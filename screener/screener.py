import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

MIN_BARS = 150   # ma120.iloc[-20] 계산에 최소 140봉 필요


def _last_weekday(dt: datetime, skip_weekends: bool = True) -> str:
    if skip_weekends:
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _calc_rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


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


def calc_signals_from_df(hist: pd.DataFrame, market_return: float = 0.0, cfg: dict = None) -> dict | None:
    """DataFrame을 직접 받아 신호 계산 (백테스트에서도 재사용)"""
    from market_config import KR_CONFIG
    if cfg is None:
        cfg = KR_CONFIG
    try:
        if hist.empty or len(hist) < MIN_BARS:
            return None

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
        ma5   = close.rolling(5).mean()
        ma20  = close.rolling(20).mean()
        ma60  = close.rolling(60).mean()
        ma120 = close.rolling(120).mean()

        ma5_v, ma20_v, ma60_v, ma120_v = (
            float(ma5.iloc[-1]), float(ma20.iloc[-1]),
            float(ma60.iloc[-1]), float(ma120.iloc[-1])
        )
        ma120_rising = float(ma120.iloc[-1]) > float(ma120.iloc[-20])

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
        obv = (close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0)) * volume).cumsum()
        obv_rising   = float(obv.iloc[-1]) > float(obv.iloc[-20])
        obv_new_high = float(obv.iloc[-1]) >= float(obv.iloc[-60:].max()) * 0.98

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

        # ── ATR (14일) + 손절가 ───────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr_14 = float(tr.rolling(14).mean().iloc[-1])
        # 가격 스케일이 시장마다 달라 반올림 자리수를 가격에 맞춤
        nd = 0 if price_now >= 1000 else 4
        stop_swing = round(price_now - 1.5 * atr_14, nd)   # 스윙 손절 (-1.5 ATR)
        stop_lt    = round(price_now - 2.5 * atr_14, nd)   # 장투 손절 (-2.5 ATR)

        return {
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
        }
    except Exception:
        return None


def _get_signals(ticker: str, start_date: str, market_return: float, cfg: dict = None) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, start_date)
        hist = drop_partial_bar(hist, cfg or {})
        return calc_signals_from_df(hist, market_return, cfg=cfg)
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
    """O'Neil CAN SLIM (기술적 요소 — EPS/기관은 추후)"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["pos_52w"] >= 0.85:                                        score += 25
    elif s["pos_52w"] >= 0.75:                                      score += 15
    if s["vol_ratio"] >= cfg["vol_ratio_buy"]:                      score += 20
    if s["vol_ratio"] >= cfg["vol_ratio_surge"]:                    score += 10
    if s["rs"] > 0.05:                                              score += 15
    if s["rs"] > 0.15:                                              score += 10
    if s["full_aligned"]:                                           score += 15
    elif s["partial_aligned"]:                                      score += 8
    if cfg["rsi_min"] <= s["rsi"] <= cfg["rsi_max"] + 5:           score += 5
    return min(score, 100.0)


def _score_vcp(s: dict, cfg: dict = None) -> float:
    """Minervini VCP (변동성 수축 패턴)"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["bb_squeeze"]:                                             score += 30
    if cfg["vcp_pullback_min"] <= s["pullback_pct"] <= cfg["vcp_pullback_max"]: score += 20
    if s["vol_contracting"]:                                        score += 15
    if s["partial_aligned"]:                                        score += 20
    if s["obv_rising"]:                                             score += 15
    return min(score, 100.0)


def _score_stage2(s: dict, cfg: dict = None) -> float:
    """Stan Weinstein Stage 2 (상승 추세 진입)"""
    score = 0.0
    if s["price"] > s["ma120"]:                            score += 25
    if s["ma120_rising"]:                                  score += 25
    if s["above_ma120_days"] >= 15:                        score += 15
    elif s["above_ma120_days"] >= 8:                       score += 8
    if s["partial_aligned"]:                               score += 15
    if s["full_aligned"]:                                  score += 5
    if s["rs"] > 0:                                        score += 10
    if s["rs"] > 0.05:                                     score += 5
    return min(score, 100.0)


def _score_wyckoff(s: dict, cfg: dict = None) -> float:
    """Wyckoff 매집 (스마트머니 추적)"""
    score = 0.0
    if s["obv_new_high"]:                                  score += 35
    elif s["obv_rising"]:                                  score += 20
    if s["bb_squeeze"]:                                    score += 20
    if s["bullish_ratio"] >= 0.65:                         score += 20
    if s["price"] > s["ma20"]:                             score += 15
    if s["price"] > s["ma60"]:                             score += 10
    return min(score, 100.0)


def _score_darvas(s: dict, cfg: dict = None) -> float:
    """Nicolas Darvas Box (박스권 돌파)"""
    from market_config import KR_CONFIG
    if cfg is None: cfg = KR_CONFIG
    score = 0.0
    if s["pos_52w"] >= 0.90:                               score += 35
    elif s["pos_52w"] >= 0.80:                             score += 20
    elif s["pos_52w"] >= 0.70:                             score += 10
    if s["vol_ratio"] >= cfg["vol_ratio_buy"]:             score += 25
    if s["vol_ratio"] >= cfg["vol_ratio_surge"]:           score += 15
    if s["momentum_3m"] > cfg["momentum_min"] * 3:         score += 15
    if s["momentum_3m"] > cfg["momentum_min"] * 6:         score += 10
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
    "p1":      lambda s, c: s["partial_aligned"] and (s["obv_rising"] or s["bb_squeeze"]),
    "p2":      lambda s, c: s["full_aligned"] and s["price_above_ma5"] and s["macd"] > 0,
    "p3":      lambda s, c: s["is_pullback_range"] and s["above_ma20"],
    "canslim": lambda s, c: s["pos_52w"] >= 0.75 and s["rs"] > 0 and s["vol_ratio"] >= c["vol_ratio_buy"] * 0.5,
    "vcp":     lambda s, c: s["bb_squeeze"] and s["vol_contracting"] and s["partial_aligned"],
    "stage2":  lambda s, c: s["price"] > s["ma120"] and s["ma120_rising"] and s["partial_aligned"] and s["rs"] > 0,
    "wyckoff": lambda s, c: s["obv_rising"] and s["bb_squeeze"] and s["price"] > s["ma20"],
    "darvas":  lambda s, c: s["pos_52w"] >= 0.80 and s["vol_ratio"] >= c["vol_ratio_buy"],
}


# ══════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════

SCORE_THRESHOLD     = 60
ALL_PATTERN_KEYS    = ["p1", "p2", "p3", "canslim", "vcp", "stage2", "wyckoff", "darvas"]
TREND_PATTERN_KEYS  = ["stage2", "canslim", "darvas"]   # 추세/돌파형 (신고가, 상승 추세)
ACCUM_PATTERN_KEYS  = ["wyckoff", "vcp"]                # 매집/수축형 (조정, 매집 완료)
CUSTOM_PATTERN_KEYS = ["p1", "p2", "p3"]                # 내 3개 패턴

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


def score_pattern(key: str, s: dict, cfg: dict) -> float:
    """필수조건 미충족 시 0점 — 스크리너와 백테스트가 동일 게이트를 공유"""
    if not _base_ok(s, cfg):
        return 0.0
    if not REQUIRED_FNS[key](s, cfg):
        return 0.0
    return SCORE_FNS[key](s, cfg)


BASE_COLS = ["ticker", "name", "market", "sector", "price", "ma5", "ma20", "ma60", "ma120",
             "rsi", "macd", "vol_ratio", "avg_value_20", "momentum_3m", "rs", "pos_52w",
             "atr_14", "stop_swing", "stop_lt"]

EXTRA_COLS = {
    "p1":      ["bb_squeeze", "obv_rising", "obv_new_high", "bullish_ratio", "ma20_just_cross"],
    "p2":      ["full_aligned", "no_ma5_break"],
    "p3":      ["pullback_pct", "in_fib_zone", "above_ma20", "today_bullish"],
    "canslim": ["near_52w_high", "rs", "full_aligned"],
    "vcp":     ["bb_squeeze", "vol_contracting", "partial_aligned", "obv_rising", "pullback_pct"],
    "stage2":  ["ma120_rising", "above_ma120_days", "rs"],
    "wyckoff": ["obv_new_high", "obv_rising", "bb_squeeze", "bullish_ratio"],
    "darvas":  ["pos_52w", "near_52w_high", "momentum_3m"],
    "common_trend": ["pos_52w", "rs", "near_52w_high", "full_aligned"],
    "common_accum": ["bb_squeeze", "obv_rising", "obv_new_high", "vol_contracting"],
    "common_all":   ["pos_52w", "rs", "full_aligned", "obv_rising"],
}


def get_universe(cfg: dict) -> list[dict]:
    """스크리닝 대상 종목 리스트 — 백테스트도 동일 유니버스를 사용"""
    from market_config import CRYPTO_TICKERS

    if cfg["type"] == "CRYPTO":
        return [{"ticker": t, "name": t.split("/")[0], "market": "CRYPTO", "sector": ""}
                for t in CRYPTO_TICKERS]

    frames = []
    for market in cfg["markets"]:
        df_mkt = fdr.StockListing(market)
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

    print(f"유니버스: {before} → {len(df)}종목 (우선주/스팩/시총 필터 적용)")
    return df[["ticker", "name", "market", "sector"]].to_dict("records")


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
    print(f"벤치마크 3M 수익률: {market_return*100:.1f}%")

    rows = get_universe(cfg)

    def fetch(row):
        s = _get_signals(row["ticker"], start_date, market_return, cfg=cfg)
        if s is None:
            return None
        scores = {f"score_{k}": score_pattern(k, s, cfg) for k in ALL_PATTERN_KEYS}
        return {**row, **s, **scores}

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
        return {k: pd.DataFrame() for k in ALL_PATTERN_KEYS + ["common_trend", "common_accum", "common_all"]}

    all_df = pd.DataFrame(results)

    tradable = all_df["is_tradable"] & (all_df["avg_value_20"] >= (cfg.get("min_trading_value") or 0))
    print(f"거래 가능 필터: {len(all_df)} → {int(tradable.sum())}종목 (거래정지/저유동성 제외)")
    all_df = all_df[tradable]
    if all_df.empty:
        return {k: pd.DataFrame() for k in ALL_PATTERN_KEYS + ["common_trend", "common_accum", "common_all"]}

    common_extra = [c for c in EXTRA_COLS.get("common_trend", []) if c in all_df.columns]

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

    # ── 공통 1순위 A: 추세/돌파형 (Stage2 + CAN SLIM + Darvas) 2개+ ──
    trend_hits = sum(
        (all_df[f"score_{k}"] >= THRESHOLD).astype(int)
        for k in TREND_PATTERN_KEYS
    )
    all_df["trend_hits"] = trend_hits
    all_df["trend_score"] = sum(
        all_df[f"score_{k}"] for k in TREND_PATTERN_KEYS
    ) / len(TREND_PATTERN_KEYS)

    output["common_trend"] = (
        all_df[all_df["trend_hits"] >= 2]
        .nlargest(20, "trend_score")
        [BASE_COLS + common_extra + ["trend_hits", "trend_score"]]
        .rename(columns={"trend_hits": "pattern_hits", "trend_score": "score"})
    )

    # ── 공통 1순위 B: 매집/수축형 (Wyckoff + VCP) 둘 다 ──────
    accum_hits = sum(
        (all_df[f"score_{k}"] >= THRESHOLD).astype(int)
        for k in ACCUM_PATTERN_KEYS
    )
    all_df["accum_hits"] = accum_hits
    all_df["accum_score"] = sum(
        all_df[f"score_{k}"] for k in ACCUM_PATTERN_KEYS
    ) / len(ACCUM_PATTERN_KEYS)

    output["common_accum"] = (
        all_df[all_df["accum_hits"] >= 2]
        .nlargest(20, "accum_score")
        [BASE_COLS + common_extra + ["accum_hits", "accum_score"]]
        .rename(columns={"accum_hits": "pattern_hits", "accum_score": "score"})
    )

    # ── 공통 3순위: 내 3개 패턴(P1+P2+P3) 2개+ ──────────────
    custom_hits = sum(
        (all_df[f"score_{k}"] >= THRESHOLD).astype(int)
        for k in CUSTOM_PATTERN_KEYS
    )
    all_df["custom_hits"] = custom_hits
    all_df["custom_score"] = sum(
        all_df[f"score_{k}"] for k in CUSTOM_PATTERN_KEYS
    ) / len(CUSTOM_PATTERN_KEYS)

    output["common_all"] = (
        all_df[all_df["custom_hits"] >= 2]
        .nlargest(20, "custom_score")
        [BASE_COLS + common_extra + ["custom_hits", "custom_score"]]
        .rename(columns={"custom_hits": "pattern_hits", "custom_score": "score"})
    )

    for k, v in output.items():
        print(f"[{k}] {len(v)}종목")

    return output
