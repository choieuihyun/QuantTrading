import numpy as np
import pandas as pd
import FinanceDataReader as fdr

import patterns
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# MA200 기울기(200+21)와 RS 4분기(252+1) 중 큰 쪽. 이보다 짧으면 원전 조건을 잴 수 없다.
MIN_BARS = 253


def _last_weekday(dt: datetime, skip_weekends: bool = True) -> str:
    if skip_weekends:
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _wilder(s: pd.Series, period: int) -> pd.Series:
    """Wilder 평활 — RSI·ATR의 표준 정의. 단순이동평균을 쓰면 다른 지표가 된다."""
    return s.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _calc_rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain = _wilder(delta.clip(lower=0), period)
    loss = _wilder(-delta.clip(upper=0), period)
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


def sanitize_ohlc(hist: pd.DataFrame) -> pd.DataFrame:
    """
    거래정지일에 FinanceDataReader는 시/고/저를 0으로 주고 종가만 직전 값으로 유지한다.
    그대로 두면 저가 0이 손절 도달로 잡혀 0원 청산(-100%)이 되고, ATR과 52주 저점도 망가진다.
    가격이 멈춘 날이므로 종가로 채운다.
    """
    if hist.empty:
        return hist
    cols = [c for c in ("Open", "High", "Low") if c in hist.columns]
    if "Close" not in hist.columns or not cols:
        return hist

    hist = hist[hist["Close"] > 0]
    bad = (hist[cols] <= 0).any(axis=1)
    if not bad.any():
        return hist

    hist = hist.copy()
    for c in cols:
        hist.loc[bad, c] = hist.loc[bad, "Close"]
    return hist


def drop_partial_bar(hist: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """24/7 시장은 진행 중인 당일 봉의 거래량이 미완성이라 vol_ratio가 왜곡됨"""
    if not cfg.get("drop_partial_bar") or hist.empty:
        return hist
    today_utc = datetime.now(timezone.utc).date()
    if hist.index[-1].date() >= today_utc:
        return hist.iloc[:-1]
    return hist


def _get_market_return(start_date: str, benchmark: str = "KS11", bars: int = 65) -> float:
    """실패 시 예외로 중단 — 조용히 0.0을 반환하면 rs가 절대 모멘텀으로 바뀜"""
    data = fdr.DataReader(benchmark, start_date)
    if data.empty or len(data) < bars + 1:
        raise RuntimeError(f"벤치마크 {benchmark} 데이터 부족 ({len(data)}행, {bars + 1}행 필요)")
    ref = float(data["Close"].iloc[-bars])
    now = float(data["Close"].iloc[-1])
    return round((now - ref) / ref, 4)


def market_uptrend_from_series(bench_close: pd.Series) -> bool:
    """
    CAN SLIM의 M — 시장 방향. O'Neil은 조정장에서 매수하지 말라고 못박는다.
    벤치마크가 자기 200일선 위에 있고 그 선이 우상향이면 상승장으로 본다.
    """
    if len(bench_close) < 221:
        return True                      # 판정 불가 시 막지 않음 (신호를 통째로 없애는 게 더 위험)
    ma200 = bench_close.rolling(200).mean()
    return bool(float(bench_close.iloc[-1]) > float(ma200.iloc[-1])
                and float(ma200.iloc[-1]) > float(ma200.iloc[-21]))


def _market_uptrend(start_date: str, cfg: dict) -> bool:
    data = fdr.DataReader(cfg["benchmark"], start_date)
    if data.empty:
        return True
    return market_uptrend_from_series(data["Close"].astype(float))


def calc_signals_from_df(hist: pd.DataFrame, market_return: float = 0.0, cfg: dict = None,
                         market_uptrend: bool = True) -> dict | None:
    """
    DataFrame을 직접 받아 신호 계산 (백테스트·재현에서도 재사용).

    market_uptrend는 CAN SLIM의 M(시장 방향) — 벤치마크가 자기 200일선 위에서 우상향인지.
    종목별로 계산할 수 없는 값이라 호출부가 넘겨준다.
    """
    from market_config import KR_CONFIG
    if cfg is None:
        cfg = KR_CONFIG
    try:
        if hist.empty or len(hist) < MIN_BARS:
            return None

        # 창 길이가 달라지면 OBV cumsum 기준선과 pos_52w 구간이 달라져 라이브와 재현이
        # 서로 다른 신호를 낸다. 두 경로 모두 여기서 동일한 봉 수로 잘라 쓴다.
        lookback = cfg.get("lookback_bars")
        if lookback and len(hist) > lookback:
            hist = hist.iloc[-lookback:]

        close  = hist["Close"]
        volume = hist["Volume"]
        open_  = hist["Open"]
        high   = hist["High"]
        low    = hist["Low"]

        price_now = float(close.iloc[-1])
        if price_now <= 0:
            return None

        # ── 거래 가능성 (거래정지·가격고정 종목 배제) ────────
        recent_vol   = volume.iloc[-20:]
        zero_vol_days = int((recent_vol.fillna(0) <= 0).sum())
        price_frozen  = float(close.iloc[-20:].std()) == 0.0
        avg_value_20  = float((close * volume).iloc[-20:].mean())
        is_tradable   = (zero_vol_days <= 2) and not price_frozen

        # ── 이동평균 ─────────────────────────────────────────
        # 5/20/60/120은 자체 패턴(P1~P3)용, 50/150/200은 원전 기법용.
        # Minervini와 Weinstein은 각각 50·150·200일선과 30주선(=150일)을 명시한다.
        ma5   = close.rolling(5).mean()
        ma20  = close.rolling(20).mean()
        ma60  = close.rolling(60).mean()
        ma120 = close.rolling(120).mean()
        ma50  = close.rolling(50).mean()
        ma150 = close.rolling(150).mean()
        ma200 = close.rolling(200).mean()

        ma5_v, ma20_v, ma60_v, ma120_v = (
            float(ma5.iloc[-1]), float(ma20.iloc[-1]),
            float(ma60.iloc[-1]), float(ma120.iloc[-1])
        )
        ma50_v, ma150_v, ma200_v = (
            float(ma50.iloc[-1]), float(ma150.iloc[-1]), float(ma200.iloc[-1])
        )
        ma120_rising = float(ma120.iloc[-1]) > float(ma120.iloc[-20])
        # Minervini 기준 3: 200일선이 최소 1개월(21거래일) 우상향
        ma200_rising = np.isfinite(ma200_v) and ma200_v > float(ma200.iloc[-21])
        ma150_rising = np.isfinite(ma150_v) and ma150_v > float(ma150.iloc[-21])

        # ── MACD (12/26/9) ───────────────────────────────────
        macd_line   = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram   = macd_line - signal_line

        # ── RSI (14) ─────────────────────────────────────────
        rsi_v = _calc_rsi(close)

        # ── 볼린저 밴드 ──────────────────────────────────────
        std20    = close.rolling(20).std()
        bb_width = (4 * std20 / ma20)
        bb_squeeze = float(bb_width.iloc[-1]) <= float(bb_width.iloc[-60:].quantile(0.25))

        # ── OBV ──────────────────────────────────────────────
        # cumsum은 넘겨받은 창의 첫 봉을 0으로 잡으므로 OBV 절대값은 창 길이에 따라 달라진다.
        # 신고점 판정을 "최고값 × 0.98"로 하면 그 기준선이 같이 움직여 라이브와 백테스트가
        # 서로 다른 값을 낸다. 60일 변동폭 대비 상대 위치로 바꿔 창 길이와 무관하게 만든다.
        obv = (close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * volume).cumsum()
        obv_win      = obv.iloc[-60:]
        obv_max      = float(obv_win.max())
        obv_range    = obv_max - float(obv_win.min())
        obv_rising   = float(obv.iloc[-1]) > float(obv.iloc[-20])
        obv_new_high = (obv_range <= 0) or (float(obv.iloc[-1]) >= obv_max - 0.02 * obv_range)

        # ── 거래량 ───────────────────────────────────────────
        vol_avg_20 = float(volume.iloc[-20:].mean())
        vol_ratio  = round(float(volume.iloc[-1]) / vol_avg_20, 2) if vol_avg_20 > 0 else 0.0
        vol_contracting = float(volume.iloc[-5:].mean()) < float(volume.iloc[-20:].mean()) * 0.8

        # ── 5일선 관련 ───────────────────────────────────────
        price_above_ma5 = price_now > ma5_v
        ma5_rising      = float(ma5.iloc[-1]) > float(ma5.iloc[-5])
        no_ma5_break    = bool((close.iloc[-5:] >= ma5.iloc[-5:] * 0.99).all())

        # ── 3개월 모멘텀 + 상대강도(RS) ─────────────────────
        ref = float(close.iloc[-65])
        momentum_3m = round((price_now - ref) / ref, 4)
        rs = round(momentum_3m - market_return, 4)
        # IBD RS Rating의 원재료 — 유니버스 백분위로 바꿔야 O'Neil의 'L'이 된다
        rs_str = patterns.rs_strength(close, cfg.get("bars_per_year", 252))

        # ── 52주 고/저점 위치 ────────────────────────────────
        # 시장별 연간 봉 수 기준 (주식 252, 코인 365)
        year_bars   = cfg.get("bars_per_year", 252)
        win         = min(year_bars, len(hist))
        high_period = float(high.iloc[-win:].max())
        low_period  = float(low.iloc[-win:].min())
        pos_52w = round((price_now - low_period) / (high_period - low_period), 4) if (high_period - low_period) > 0 else 0.5
        near_52w_high = pos_52w >= 0.75
        pos_52w_full  = len(hist) >= year_bars

        # ── 정배열 ────────────────────────────────────────────
        full_aligned    = ma5_v > ma20_v > ma60_v > ma120_v
        partial_aligned = ma5_v > ma20_v > ma60_v
        ma20_just_cross = (float(ma20.iloc[-1]) > float(ma60.iloc[-1]) and
                           float(ma20.iloc[-10]) <= float(ma60.iloc[-10]))
        ma60_just_cross = (float(ma60.iloc[-1]) > float(ma120.iloc[-1]) and
                           float(ma60.iloc[-20]) <= float(ma120.iloc[-20]))

        # ── 눌림목 ───────────────────────────────────────────
        recent_high       = float(close.iloc[-25:-3].max())
        pullback_pct      = (price_now - recent_high) / recent_high
        prior_low         = float(close.iloc[-85:-25].min())
        fib_38            = recent_high - (recent_high - prior_low) * 0.382
        fib_62            = recent_high - (recent_high - prior_low) * 0.618
        in_fib_zone       = bool(fib_62 <= price_now <= fib_38)
        is_pullback_range = bool(cfg["pullback_min"] <= pullback_pct <= cfg["pullback_max"])
        today_bullish     = float(close.iloc[-1]) > float(open_.iloc[-1])

        # ── 양봉 비율 ─────────────────────────────────────────
        candle_dir    = close.iloc[-20:].values - open_.iloc[-20:].values
        bullish_ratio = float((candle_dir > 0).mean())

        # ── Stage 2 유지 기간 (MA120 위 거래일 수) ───────────
        above_ma120_days = int((close.iloc[-20:].values > ma120.iloc[-20:].values).sum())

        # ── 원전 기법용 구조 탐지 ─────────────────────────────
        h_np, l_np, c_np, v_np = (high.to_numpy(dtype=float), low.to_numpy(dtype=float),
                                  close.to_numpy(dtype=float), volume.to_numpy(dtype=float))
        box  = patterns.darvas_box(h_np, l_np, c_np,
                                   max_width=cfg.get("box_max_width", patterns.BOX_MAX_WIDTH))
        vcp  = patterns.vcp_state(h_np, l_np, c_np, v_np)
        rng  = patterns.trading_range(h_np, l_np,
                                      max_width=cfg.get("base_max_width", patterns.BASE_MAX_WIDTH))
        wyck = patterns.wyckoff_state(h_np, l_np, c_np, v_np, rng)

        # Weinstein Stage 2 진입 = 베이스 저항을 거래량 동반해 돌파. 이미 오른 상태가 아니라 '전환'.
        range_high = rng.get("range_high")
        broke_base = bool(range_high and price_now > range_high)
        # 돌파 시점을 놓치지 않도록 최근 10봉 내 돌파도 인정
        recent_break = False
        breakout_vol = 0.0
        if range_high and vol_avg_20 > 0:
            tail_c = close.iloc[-10:].to_numpy(dtype=float)
            tail_v = volume.iloc[-10:].to_numpy(dtype=float)
            mask = tail_c > range_high
            recent_break = bool(mask.any())
            # 돌파가 일어난 봉의 거래량 배수 — Weinstein은 평균 2배 이상을 요구한다
            if recent_break:
                breakout_vol = round(float(tail_v[mask].max()) / vol_avg_20, 2)

        # Minervini Trend Template — 원전은 8개 중 하나라도 빠지면 탈락.
        # 8번(RS Rating ≥ 70)은 유니버스 백분위라 여기서 못 구한다 → 스코어링 단계에서 합친다.
        above_52w_low = low_period > 0 and (price_now / low_period - 1) >= 0.30   # 기준 6 (책 기준 30%)
        tt = [
            price_now > ma150_v and price_now > ma200_v,   # 1
            ma150_v > ma200_v,                             # 2
            ma200_rising,                                  # 3
            ma50_v > ma150_v and ma50_v > ma200_v,         # 4
            price_now > ma50_v,                            # 5
            above_52w_low,                                 # 6
            near_52w_high,                                 # 7
        ]
        tt_ok = all(bool(x) for x in tt)
        tt_hits = int(sum(bool(x) for x in tt))

        # ── ATR (14일) + 손절가 ───────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_14 = float(_wilder(tr, 14).iloc[-1])
        # 가격 스케일이 시장마다 달라 반올림 자리수를 가격에 맞춤
        nd = 0 if price_now >= 1000 else 4
        stop_swing = round(price_now - 1.5 * atr_14, nd)   # 스윙 손절 (-1.5 ATR)
        stop_lt    = round(price_now - 2.5 * atr_14, nd)   # 장투 손절 (-2.5 ATR)

        return {
            # 시계가 아니라 데이터의 마지막 봉 날짜. UTC 러너에서 08:30 KST 실행 시
            # datetime.today()가 실제 시세 날짜와 최대 이틀까지 어긋난다(월요일 아침).
            "bar_date":           str(hist.index[-1].date()),
            "price":              price_now,
            "ma5":                round(ma5_v, nd),
            "ma20":               round(ma20_v, nd),
            "ma60":               round(ma60_v, nd),
            "ma120":              round(ma120_v, nd),
            "ma120_rising":       bool(ma120_rising),
            "macd":               round(float(macd_line.iloc[-1]), 4),
            "macd_signal":        round(float(signal_line.iloc[-1]), 4),
            "macd_hist":          round(float(histogram.iloc[-1]), 4),
            "macd_hist_prev":     round(float(histogram.iloc[-2]), 4),
            "rsi":                round(rsi_v, 1),
            "bb_squeeze":         bool(bb_squeeze),
            "obv_rising":         bool(obv_rising),
            "obv_new_high":       bool(obv_new_high),
            "vol_ratio":          vol_ratio,
            "vol_contracting":    bool(vol_contracting),
            "avg_value_20":       round(avg_value_20, 0),
            "is_tradable":        bool(is_tradable),
            "price_above_ma5":    bool(price_above_ma5),
            "ma5_rising":         bool(ma5_rising),
            "no_ma5_break":       bool(no_ma5_break),
            "momentum_3m":        momentum_3m,
            "rs":                 rs,
            "pos_52w":            pos_52w,
            "near_52w_high":      bool(near_52w_high),
            "pos_52w_full":       bool(pos_52w_full),
            "full_aligned":       bool(full_aligned),
            "partial_aligned":    bool(partial_aligned),
            "ma20_just_cross":    bool(ma20_just_cross),
            "ma60_just_cross":    bool(ma60_just_cross),
            "pullback_pct":       round(pullback_pct, 4),
            "in_fib_zone":        bool(in_fib_zone),
            "is_pullback_range":  bool(is_pullback_range),
            "above_ma20":         bool(price_now > ma20_v),
            "today_bullish":      bool(today_bullish),
            "bullish_ratio":      round(bullish_ratio, 2),
            "above_ma120_days":   above_ma120_days,
            "atr_14":             round(atr_14, nd),
            "stop_swing":         stop_swing,
            "stop_lt":            stop_lt,

            # ── 원전 기법용 ───────────────────────────────────
            "ma50":               round(ma50_v, nd),
            "ma150":              round(ma150_v, nd),
            "ma200":              round(ma200_v, nd),
            "ma150_rising":       bool(ma150_rising),
            "ma200_rising":       bool(ma200_rising),
            "above_52w_low":      bool(above_52w_low),
            "tt_hits":            tt_hits,
            "tt_ok":              bool(tt_ok),        # RS Rating(8번) 제외한 7개
            "rs_strength":        rs_str,             # 유니버스 백분위 전 단계
            "market_uptrend":     bool(market_uptrend),
            # Darvas
            "box_top":            None if box["box_top"] is None else round(box["box_top"], nd),
            "box_bottom":         None if box["box_bottom"] is None else round(box["box_bottom"], nd),
            "box_bars":           box["box_bars"],
            "box_ready":          bool(box["box_ready"]),
            # Darvas 원전 손절 = 박스 바닥. ATR 손절과 다른 값이므로 별도 필드로 둔다.
            "stop_box":           None if box["box_bottom"] is None else round(box["box_bottom"], nd),
            "box_breakout":       bool(box["box_breakout"]),
            # Minervini VCP
            "vcp_legs":           vcp["vcp_legs"],
            "vcp_tightening":     bool(vcp["vcp_tightening"]),
            "vcp_vol_declining":  bool(vcp["vcp_vol_declining"]),
            "vcp_last_depth":     vcp["vcp_last_depth"],
            "vcp_pivot":          None if vcp["vcp_pivot"] is None else round(vcp["vcp_pivot"], nd),
            "vcp_above_pivot":    bool(vcp["vcp_above_pivot"]),
            # Weinstein 베이스 / Wyckoff 거래범위
            "range_high":         None if range_high is None else round(range_high, nd),
            "range_low":          None if rng["range_low"] is None else round(rng["range_low"], nd),
            "range_width":        rng["range_width"],
            "base_breakout":      bool(broke_base),
            "recent_breakout":    bool(recent_break),
            "breakout_vol":       breakout_vol,
            # Wyckoff (구조적으로 확인 가능한 부분만)
            "wyckoff_spring":     bool(wyck["spring"]),
            "wyckoff_sos":        bool(wyck["sos"]),
            "wyckoff_vol_dry":    bool(wyck["vol_dry_down"]),
            "wyckoff_in_range":   bool(wyck["in_range"]),
        }
    except Exception:
        return None


# 성적표가 "N일 전에 샀으면"을 계산할 때 쓸 종가 이력 길이.
# 진입가를 저장해두고 나중 시세와 비교하면, 그 사이 액면분할·무상증자가 있었을 때
# 조정 전 가격과 조정 후 가격을 비교하게 되어 -50%짜리 가짜 손실이 찍힌다.
# 같은 시점에 받은 하나의 시계열에서 두 날짜를 모두 읽어야 한다.
CLOSE_HISTORY_BARS = 90


def _get_signals(ticker: str, start_date: str, market_return: float, cfg: dict = None,
                 market_uptrend: bool = True, closes: dict = None) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, start_date)
        hist = sanitize_ohlc(drop_partial_bar(hist, cfg or {}))
        s = calc_signals_from_df(hist, market_return, cfg=cfg, market_uptrend=market_uptrend)
        if s is not None and closes is not None:
            tail = hist["Close"].iloc[-CLOSE_HISTORY_BARS:]
            closes[str(ticker)] = {str(d.date()): float(v) for d, v in tail.items()}
        return s
    except Exception:
        return None


# ══════════════════════════════════════════════════════
# 스코어링 함수
# ══════════════════════════════════════════════════════

def _score_p1(s: dict, cfg: dict = None) -> float:
    """정배열 퍼지기 직전 + 매집"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["partial_aligned"]:                                        score += 20
    if s["ma20_just_cross"]:                                        score += 15
    if s["ma60_just_cross"]:                                        score += 10
    if s["bb_squeeze"]:                                             score += 20
    if s["obv_rising"]:                                             score += 15
    if s["obv_new_high"]:                                           score += 10
    if s["bullish_ratio"] >= 0.6:                                   score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:                        score += 10
    if s["rsi"] >= cfg["rsi_min"]:                                  score += 5
    if cfg["vol_ratio_buy"] * 0.6 <= s["vol_ratio"] <= cfg["vol_ratio_surge"]: score += 5
    return min(score, 100.0)


def _score_p2(s: dict, cfg: dict = None) -> float:
    """5일선 타고 올라가는 추세 + 거래량 터짐"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["full_aligned"]:                                           score += 20
    if s["price_above_ma5"]:                                        score += 10
    if s["ma5_rising"]:                                             score += 10
    if s["no_ma5_break"]:                                           score += 10
    if s["macd"] > 0:                                               score += 10
    if s["macd"] > s["macd_signal"]:                                score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:                        score += 5
    if cfg["rsi_min"] <= s["rsi"] <= cfg["rsi_max"]:                score += 10
    elif cfg["rsi_max"] < s["rsi"] <= cfg["rsi_overbought"]:        score += 3
    if s["vol_ratio"] >= cfg["vol_ratio_buy"]:                      score += 10
    if s["vol_ratio"] >= cfg["vol_ratio_surge"]:                    score += 5
    if s["obv_new_high"]:                                           score += 5
    if s["momentum_3m"] > cfg["momentum_min"] * 2:                  score += 5
    return min(score, 100.0)


def _score_p3(s: dict, cfg: dict = None) -> float:
    """눌림목"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["is_pullback_range"]:                                      score += 25
    if s["in_fib_zone"]:                                            score += 20
    if s["above_ma20"]:                                             score += 15
    if s["today_bullish"]:                                          score += 10
    if s["partial_aligned"] or s["full_aligned"]:                   score += 10
    if s["macd_hist"] > s["macd_hist_prev"] and s["macd_hist"] < 0: score += 10
    if cfg["rsi_pb_min"] <= s["rsi"] <= cfg["rsi_pb_max"]:          score += 10
    return min(score, 100.0)


def _score_canslim(s: dict, cfg: dict = None) -> float:
    """
    O'Neil CAN SLIM — 구현 가능한 4개(N/S/L/M)로 채점.
      C 현분기 EPS +25%   : DART로 수집하지만 유니버스 전체 재무를 못 받아 선정에는 미반영
                            (main.py가 선정 후 병합하며 canslim_c로 표시)
      A 3년 연속 이익증가 : DART 8~10분기(약 2년)뿐이라 판정 불가
      N 신고가            : pos_52w
      S 거래량 급증       : vol_ratio
      L 시장 주도주       : rs_rating (유니버스 백분위, IBD 방식)
      I 기관 매수         : 데이터 없음 (외인/기관 순매수 연동 예정)
      M 시장 방향         : 벤치마크가 자기 200일선 위 + 우상향
    """
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    rsr = s.get("rs_rating") or 0
    score = 0.0
    if s["pos_52w"] >= 0.90:                               score += 25   # N
    elif s["pos_52w"] >= 0.75:                             score += 15
    if rsr >= 90:                                          score += 30   # L
    elif rsr >= 80:                                        score += 22
    elif rsr >= 70:                                        score += 15
    if s["vol_ratio"] >= cfg["vol_ratio_surge"]:           score += 20   # S
    elif s["vol_ratio"] >= cfg["vol_ratio_buy"]:           score += 13
    if s.get("market_uptrend"):                            score += 15   # M
    if s.get("tt_ok"):                                     score += 10   # 추세 건전성
    return min(score, 100.0)


def _score_vcp(s: dict, cfg: dict = None) -> float:
    """
    Minervini VCP — 조정이 연속으로 얕아지는 것이 정체성.
    Trend Template 8개(7개 + RS Rating)를 먼저 통과해야 한다.
    """
    score = 0.0
    if s.get("vcp_tightening"):                            score += 30
    legs = s.get("vcp_legs") or 0
    if legs >= 3:                                          score += 15   # 교과서 3회 이상
    elif legs == 2:                                        score += 8
    if s.get("vcp_vol_declining"):                         score += 20   # 매물 소진
    depth = s.get("vcp_last_depth")
    if depth is not None and depth <= 0.10:                score += 20   # 마지막 수축이 타이트
    elif depth is not None and depth <= 0.15:              score += 12
    if s.get("vcp_above_pivot"):                           score += 15   # 피벗 돌파
    return min(score, 100.0)


def _score_stage2(s: dict, cfg: dict = None) -> float:
    """
    Weinstein Stage 2 — 30주선(=150일선) 기준. 상승 '상태'가 아니라 베이스 저항 '돌파'가 진입점.
    주봉 대신 일봉 150선을 쓰는 것은 근사다 (30주 = 150거래일).
    """
    score = 0.0
    if s["price"] > s.get("ma150", 0):                     score += 20
    if s.get("ma150_rising"):                              score += 20
    if s.get("base_breakout"):                             score += 20   # 오늘 저항 돌파
    elif s.get("recent_breakout"):                         score += 12   # 최근 10봉 내 돌파
    bv = s.get("breakout_vol") or 0
    if bv >= 3.0:                                          score += 20   # 원전: 평균 2~3배
    elif bv >= 2.0:                                        score += 14
    rsr = s.get("rs_rating") or 0
    if rsr >= 70:                                          score += 12   # 시장 대비 강세
    elif rsr >= 50:                                        score += 6
    if s["price"] > s.get("ma200", 0):                     score += 8
    return min(score, 100.0)


def _score_wyckoff(s: dict, cfg: dict = None) -> float:
    """
    Wyckoff 매집 — 구조적으로 확인 가능한 부분만.
    국면(A~E)과 SC/AR/ST 식별은 거래량-스프레드 재량 해석이라 구현하지 않았다.
    """
    score = 0.0
    if s.get("wyckoff_spring"):                            score += 30   # 하단 이탈 후 회복
    if s.get("wyckoff_sos"):                               score += 30   # 거래량 동반 상단 돌파
    if s.get("wyckoff_vol_dry"):                           score += 20   # 하락일 거래량 < 상승일
    if s["obv_rising"]:                                    score += 12
    if s["obv_new_high"]:                                  score += 8
    return min(score, 100.0)


def _score_darvas(s: dict, cfg: dict = None) -> float:
    """
    Darvas Box — 박스 천장 돌파. 손절은 ATR이 아니라 박스 바닥(stop_box).
    """
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s.get("box_breakout"):                              score += 35
    if s["vol_ratio"] >= cfg["vol_ratio_surge"]:           score += 25
    elif s["vol_ratio"] >= cfg["vol_ratio_buy"]:           score += 18
    top, bot = s.get("box_top"), s.get("box_bottom")
    if top and bot and bot > 0:
        width = (top - bot) / bot
        if width <= 0.10:                                  score += 20   # 좁을수록 좋은 박스
        elif width <= 0.18:                                score += 12
    if s["pos_52w"] >= 0.90:                               score += 20   # 신고가권에서의 박스
    elif s["pos_52w"] >= 0.75:                             score += 12
    return min(score, 100.0)


# ══════════════════════════════════════════════════════
# 필수조건 게이트
# ══════════════════════════════════════════════════════
# 가중합만 쓰면 패턴의 핵심과 무관한 조건들로도 임계값을 넘김.
# (예: Stage2는 "MA120 위 + 우상향" 2개만으로 50점 → 통과)
# 각 패턴의 정의상 반드시 성립해야 하는 조건을 통과 조건으로 분리.

def _base_ok(s: dict, cfg: dict) -> bool:
    if not s["is_tradable"]:
        return False
    min_value = cfg.get("min_trading_value")
    if min_value and s["avg_value_20"] < min_value:
        return False
    return True


REQUIRED_FNS = {
    # 자체 패턴 — 한국 시장용으로 직접 정한 조건
    "p1":      lambda s, c: s["partial_aligned"] and (s["obv_rising"] or s["bb_squeeze"]),
    "p2":      lambda s, c: s["full_aligned"] and s["price_above_ma5"] and s["macd"] > 0,
    "p3":      lambda s, c: s["is_pullback_range"] and s["above_ma20"],

    # 원전 기법 — 각 방법론이 "이게 없으면 그 패턴이 아니다"라고 규정한 조건
    # CAN SLIM: N(신고가) + L(RS 70↑) + M(시장 상승) + S(거래량). C/A/I는 데이터 제약으로 제외.
    "canslim": lambda s, c: (s["pos_52w"] >= 0.75
                             and (s.get("rs_rating") or 0) >= 70
                             and s.get("market_uptrend")
                             and s["vol_ratio"] >= c["vol_ratio_buy"]),
    # VCP: Trend Template 8개(7개 + RS 70) 통과 + 연속 수축이 실제로 좁아지는 중
    "vcp":     lambda s, c: (s.get("tt_ok")
                             and (s.get("rs_rating") or 0) >= 70
                             and (s.get("vcp_legs") or 0) >= 2
                             and s.get("vcp_tightening")),
    # Stage 2: 30주선(150일선) 위 + 우상향 + 베이스 저항 돌파. 상승 '상태'가 아니라 '전환'.
    "stage2":  lambda s, c: (s["price"] > s.get("ma150", 0)
                             and s.get("ma150_rising")
                             and s.get("recent_breakout")
                             and (s.get("breakout_vol") or 0) >= 2.0),
    # Wyckoff: 거래범위가 있고, Spring 또는 SOS가 관측되며, 하락일 거래량이 마른 상태
    "wyckoff": lambda s, c: (s.get("range_high") is not None
                             and (s.get("wyckoff_spring") or s.get("wyckoff_sos"))
                             and s.get("wyckoff_vol_dry")),
    # Darvas: 박스가 확정됐고 천장을 거래량과 함께 돌파
    "darvas":  lambda s, c: (s.get("box_ready")
                             and s.get("box_breakout")
                             and s["vol_ratio"] >= c["vol_ratio_buy"]),
}


# ══════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════

SCORE_THRESHOLD     = 60
ALL_PATTERN_KEYS    = ["p1", "p2", "p3", "canslim", "vcp", "stage2", "wyckoff", "darvas"]
# 원전 재구현 후 각 기법이 요구하는 국면이 갈렸다.
#   돌파형 : stage2(베이스 저항 돌파) · canslim(신고가) · darvas(박스 천장 돌파) · vcp(피벗 돌파)
#            → 모두 "저항을 뚫는 순간"을 잡는다. 서로 다른 방식으로 같은 사건을 확인.
#   매집형 : wyckoff — 거래범위 안에서의 매집. VCP는 Trend Template(상승 추세)을 요구하므로
#            횡보 매집과 동시에 성립하기 어렵다. 예전처럼 둘을 AND로 묶으면 영원히 비어 있게 된다.
TREND_PATTERN_KEYS  = ["stage2", "canslim", "darvas", "vcp"]   # 돌파형 — 2개 이상 겹치면 신뢰도↑
ACCUM_PATTERN_KEYS  = ["wyckoff"]                              # 매집형 — 현재 1개 (단독 판정)
CUSTOM_PATTERN_KEYS = ["p1", "p2", "p3"]                       # 내 3개 패턴

SCORE_FNS = {
    "p1":      _score_p1,
    "p2":      _score_p2,
    "p3":      _score_p3,
    "canslim": _score_canslim,
    "vcp":     _score_vcp,
    "stage2":  _score_stage2,
    "wyckoff": _score_wyckoff,
    "darvas":  _score_darvas,
}


def rs_rating_from_pct(pct: pd.Series) -> pd.Series:
    """
    백분위(0~1)를 IBD RS Rating(1~99)로. 라이브와 재현이 반드시 같은 식을 써야 하므로
    변환은 여기 한 곳에만 둔다.
    """
    return (pct * 98 + 1).round(0)


def attach_rs_rating(df: pd.DataFrame) -> pd.DataFrame:
    """
    IBD RS Rating(1~99) — rs_strength를 유니버스 백분위로 환산.

    O'Neil의 L은 "코스피보다 몇 % 더 올랐나"가 아니라 "전 종목 중 몇 등인가"다.
    종목 하나만 봐서는 구할 수 없어 전체를 모은 뒤 한 번에 계산한다.
    모집단은 거래 가능 종목 — 라이브와 재현이 같은 기준을 써야 값이 일치한다.

    재현은 날짜별로 나눠야 하므로 groupby로 같은 계산을 한다 (replay.build 참고).
    """
    if "rs_strength" not in df.columns or df.empty:
        df["rs_rating"] = None
        return df
    df["rs_rating"] = rs_rating_from_pct(df["rs_strength"].rank(pct=True, na_option="keep"))
    return df


def score_pattern(key: str, s: dict, cfg: dict) -> float:
    """필수조건 미충족 시 0점 — 스크리너와 백테스트가 동일 게이트를 공유"""
    if not _base_ok(s, cfg):
        return 0.0
    if not REQUIRED_FNS[key](s, cfg):
        return 0.0
    return SCORE_FNS[key](s, cfg)


BASE_COLS = ["ticker", "name", "market", "sector", "marcap", "price", "ma5", "ma20", "ma60", "ma120",
             "rsi", "macd", "vol_ratio", "avg_value_20", "momentum_3m", "rs", "rs_rating", "pos_52w",
             "atr_14", "stop_swing", "stop_lt"]

EXTRA_COLS = {
    "p1":      ["bb_squeeze", "obv_rising", "obv_new_high", "bullish_ratio", "ma20_just_cross"],
    "p2":      ["full_aligned", "no_ma5_break"],
    "p3":      ["pullback_pct", "in_fib_zone", "above_ma20", "today_bullish"],
    "canslim": ["rs_rating", "near_52w_high", "market_uptrend", "tt_ok"],
    "vcp":     ["tt_ok", "rs_rating", "vcp_legs", "vcp_last_depth", "vcp_above_pivot", "vcp_pivot"],
    "stage2":  ["ma150", "ma150_rising", "range_high", "base_breakout", "breakout_vol", "rs_rating"],
    "wyckoff": ["wyckoff_spring", "wyckoff_sos", "wyckoff_vol_dry", "range_high", "range_low", "obv_rising"],
    "darvas":  ["box_top", "box_bottom", "stop_box", "box_bars", "pos_52w"],
    "common_trend": ["pos_52w", "rs_rating", "near_52w_high", "tt_ok", "market_uptrend"],
    "common_accum": ["wyckoff_spring", "wyckoff_sos", "vcp_legs", "vcp_tightening", "obv_rising"],
    "common_all":   ["pos_52w", "rs", "full_aligned", "obv_rising"],
}


# KRX 종목 리스트를 KRX 서버를 거치지 않고 받는 경로.
#
# fdr.StockListing("KOSPI")는 "최신 영업일이 언제냐"만 data.krx.co.kr에 물어보고
# 실제 CSV는 GitHub 미러에서 받는다. 그런데 KRX가 Akamai 엣지에서 데이터센터 IP를
# 차단해(2026-08, "Access Denied") GitHub Actions에서는 그 한 번의 조회가 403이 되고
# 종목 리스트 자체를 못 받아 KR 스크리닝이 통째로 죽는다.
# 날짜를 오늘부터 거꾸로 훑어 찾으면 KRX를 아예 안 거친다.
KRX_MIRROR = ("https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache"
              "/refs/heads/master/data/listing/krx/{date}.csv")
KRX_MARKET_ID = {"KOSPI": "STK", "KOSDAQ": "KSQ", "KONEX": "KNX"}
_krx_cache: dict = {}


def krx_listing(market: str, max_back: int = 14) -> pd.DataFrame:
    """market: KOSPI | KOSDAQ | KONEX. 실패 시 fdr.StockListing으로 되돌아간다."""
    if "df" not in _krx_cache:
        import requests
        today = datetime.today().date()
        for i in range(max_back):
            day = (today - timedelta(days=i)).isoformat()
            try:
                r = requests.get(KRX_MIRROR.format(date=day), timeout=20)
            except Exception:
                continue
            if r.status_code != 200:
                continue
            import io
            _krx_cache["df"] = pd.read_csv(
                io.StringIO(r.text), index_col=0,
                dtype={"Code": str, "Dept": str, "ChangeCode": str, "MarketId": str})
            _krx_cache["date"] = day
            print(f"KRX 종목 리스트: GitHub 미러 {day} ({len(_krx_cache['df'])}종목)")
            break
        else:
            print(f"KRX 미러에서 최근 {max_back}일치를 못 찾음 — fdr.StockListing으로 시도")
            _krx_cache["df"] = None

    df = _krx_cache.get("df")
    if df is None:
        return fdr.StockListing(market)

    mid = KRX_MARKET_ID.get(market)
    out = df if mid is None else df[df["MarketId"] == mid]
    return out.reset_index(drop=True)


def get_universe(cfg: dict) -> list[dict]:
    """스크리닝 대상 종목 리스트 — 백테스트도 동일 유니버스를 사용"""
    from market_config import CRYPTO_TICKERS

    if cfg["type"] == "CRYPTO":
        return [{"ticker": t, "name": t.split("/")[0], "market": "CRYPTO", "sector": "", "marcap": None}
                for t in CRYPTO_TICKERS]

    frames = []
    for market in cfg["markets"]:
        df_mkt = krx_listing(market) if market in KRX_MARKET_ID else fdr.StockListing(market)
        df_mkt["market"] = market
        frames.append(df_mkt)

    df = pd.concat(frames, ignore_index=True)

    # 티커/이름 컬럼 통일
    for src, dst in [("Symbol", "ticker"), ("Code", "ticker"), ("Name", "name")]:
        if src in df.columns and dst not in df.columns:
            df = df.rename(columns={src: dst})
    df = df.loc[:, ~df.columns.duplicated()]

    before = len(df)

    # 우선주/신주인수권 제외 — KRX 보통주는 종목코드 끝자리가 0
    if cfg.get("common_stock_only"):
        df = df[df["ticker"].astype(str).str.endswith("0")]

    # 스팩/리츠 등 모멘텀 스크리닝에 부적합한 종목 제외
    pattern = cfg.get("exclude_name_patterns")
    if pattern and "name" in df.columns:
        df = df[~df["name"].astype(str).str.contains(pattern, na=False)]

    if cfg.get("min_marcap") and "Marcap" in df.columns:
        df = df[df["Marcap"] > cfg["min_marcap"]]
    if "Close" in df.columns:
        df = df[df["Close"] > 0]

    sector_col = next((c for c in df.columns if c.lower() in ("sector", "industry", "dept")), None)
    if sector_col:
        df = df.rename(columns={sector_col: "sector"})
    else:
        df["sector"] = ""

    # 시가총액 — PER/PBR/PSR 계산용(= 시총 ÷ DART 재무값). US/코인은 없으면 None.
    df["marcap"] = df["Marcap"] if "Marcap" in df.columns else None

    print(f"유니버스: {before} → {len(df)}종목 (우선주/스팩/시총 필터 적용)")
    return df[["ticker", "name", "market", "sector", "marcap"]].to_dict("records")


def run(cfg: dict = None) -> dict:
    from market_config import KR_CONFIG
    if cfg is None:
        cfg = KR_CONFIG

    today      = datetime.today()
    skip_wknd  = cfg.get("skip_weekends", True)
    start_date = _last_weekday(today - timedelta(days=cfg.get("data_days", 420)), skip_weekends=skip_wknd)
    THRESHOLD  = cfg.get("score_threshold", SCORE_THRESHOLD)

    print(f"\n=== {cfg['name']} 스크리닝 ===")
    print(f"벤치마크 수익률 계산 중 ({cfg['benchmark']})...")
    market_return = _get_market_return(start_date, benchmark=cfg["benchmark"])
    market_uptrend = _market_uptrend(start_date, cfg)
    print(f"벤치마크 3M 수익률: {market_return*100:.1f}% | 시장 방향(CAN SLIM M): "
          f"{'상승' if market_uptrend else '조정/하락'}")

    rows = get_universe(cfg)

    # 스코어링은 여기서 하지 않는다 — RS Rating이 유니버스 백분위라 전 종목을 모아야 구해진다.
    closes: dict = {}          # {ticker: {날짜: 종가}} — 성적표가 같은 시계열에서 두 날짜를 읽도록

    def fetch(row):
        s = _get_signals(row["ticker"], start_date, market_return, cfg=cfg,
                         market_uptrend=market_uptrend, closes=closes)
        return None if s is None else {**row, **s}

    results, failed = [], 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            if r:
                results.append(r)
            else:
                failed += 1
            if i % 50 == 0:
                print(f"진행: {i}/{len(rows)}")

    fail_pct = failed / len(rows) * 100 if rows else 0
    print(f"분석 완료: {len(results)}종목 성공 / {failed}종목 실패 ({fail_pct:.1f}%)")
    if fail_pct > 30:
        print(f"  ⚠ 실패율이 높습니다 — 데이터 소스 rate limit 또는 상장기간 부족 의심")

    if not results:
        return {k: pd.DataFrame() for k in ALL_PATTERN_KEYS + ["common_trend", "common_accum", "common_all"]}, {}

    all_df = pd.DataFrame(results)

    # as_completed는 완료 순서라 동점 종목의 화면 순서가 실행마다 달라진다.
    # 게이트만 넘으면 만점이 되는 패턴은 상위 30이 통째로 동점이라 목록 자체가 바뀐다.
    all_df = all_df.sort_values("ticker").reset_index(drop=True)

    tradable = all_df["is_tradable"] & (all_df["avg_value_20"] >= (cfg.get("min_trading_value") or 0))
    print(f"거래 가능 필터: {len(all_df)} → {int(tradable.sum())}종목 (거래정지/저유동성 제외)")
    all_df = all_df[tradable].copy()
    if all_df.empty:
        return {k: pd.DataFrame() for k in ALL_PATTERN_KEYS + ["common_trend", "common_accum", "common_all"]}, {}

    # RS Rating은 거래 가능 종목만을 모집단으로 삼는다 (재현 경로도 동일 기준)
    all_df = attach_rs_rating(all_df)
    rows_d = all_df.to_dict("records")
    for key in ALL_PATTERN_KEYS:
        all_df[f"score_{key}"] = [score_pattern(key, r, cfg) for r in rows_d]
    print(f"RS Rating 산출: 모집단 {len(all_df)}종목 | 70↑ {int((all_df['rs_rating'] >= 70).sum())}종목")

    output = {}
    for key in ALL_PATTERN_KEYS:
        col = f"score_{key}"
        extra = [c for c in EXTRA_COLS.get(key, []) if c in all_df.columns]
        output[key] = (
            all_df[all_df[col] >= THRESHOLD]
            .nlargest(30, col)
            [BASE_COLS + extra + [col]]
            .rename(columns={col: "score"})
        )

    # ── 공통 추출 ────────────────────────────────────────
    # 서로 다른 기법이 같은 종목을 동시에 가리키면 신뢰도가 올라간다는 발상.
    # 실측 반박: analyze_combos.py 기준 common_trend 20일 선정력 −0.20%(t=−0.20)로,
    # 겹치기 전 stage2 단독 +1.92%보다 나쁘다. 게이트는 유지하되 근거 없음을 화면에 표기했다.
    # 구성 패턴이 1개뿐인 카테고리에 "2개 이상"을 요구하면 영원히 비어 있으므로 개수에 맞춘다.
    for name, keys, hits_col, score_col in [
        ("common_trend", TREND_PATTERN_KEYS,  "trend_hits",  "trend_score"),
        ("common_accum", ACCUM_PATTERN_KEYS,  "accum_hits",  "accum_score"),
        ("common_all",   CUSTOM_PATTERN_KEYS, "custom_hits", "custom_score"),
    ]:
        need = min(2, len(keys))
        all_df[hits_col] = sum((all_df[f"score_{k}"] >= THRESHOLD).astype(int) for k in keys)
        all_df[score_col] = sum(all_df[f"score_{k}"] for k in keys) / len(keys)
        output[name] = (
            all_df[all_df[hits_col] >= need]
            .nlargest(20, score_col)
            [BASE_COLS + [c for c in EXTRA_COLS.get(name, []) if c in all_df.columns]
             + [hits_col, score_col]]
            .rename(columns={hits_col: "pattern_hits", score_col: "score"})
        )

    for k, v in output.items():
        print(f"[{k}] {len(v)}종목")

    # 과거에 뽑혔던 종목의 '지금 가격'을 알아야 성적표를 만들 수 있다.
    # 유니버스 전체 시세를 이미 받아둔 상태라 여기서 넘기면 추가 조회가 필요 없다.
    prices = {str(t): float(p) for t, p in zip(all_df["ticker"], all_df["price"])}
    # 가상 매매에서 종목을 검색해 담으려면 코드만으로는 부족하다.
    names = {str(t): str(n) for t, n in zip(all_df["ticker"], all_df["name"])}
    # 종목마다 상장·거래정지로 마지막 봉이 다를 수 있어 최빈값을 시장 기준일로 쓴다
    bar_date = all_df["bar_date"].mode()
    meta = {"bar_date": str(bar_date.iloc[0]) if len(bar_date) else None,
            # 종목 조회 화면이 상위 20위 밖 종목도 설명할 수 있으려면 전 종목 신호가 필요하다
            "rows": all_df.to_dict("records"),
            "closes": closes}
    return output, prices, names, meta
