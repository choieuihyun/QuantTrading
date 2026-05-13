import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


def _last_weekday(dt: datetime) -> str:
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _calc_rsi(close: pd.Series, period=14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, float("nan"))
    return float((100 - 100 / (1 + rs)).iloc[-1])


def _get_market_return(start_date: str) -> float:
    try:
        kospi = fdr.DataReader("KS11", start_date)
        if kospi.empty or len(kospi) < 2:
            return 0.0
        ref = float(kospi["Close"].iloc[-65]) if len(kospi) >= 65 else float(kospi["Close"].iloc[0])
        now = float(kospi["Close"].iloc[-1])
        return round((now - ref) / ref, 4)
    except Exception:
        return 0.0


def _get_signals(ticker: str, start_date: str, market_return: float) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, start_date)
        if hist.empty or len(hist) < 120:
            return None

        close  = hist["Close"]
        volume = hist["Volume"]
        open_  = hist["Open"]
        high   = hist["High"]
        low    = hist["Low"]

        price_now = float(close.iloc[-1])
        if price_now <= 0:
            return None

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
        ref = float(close.iloc[-65]) if len(hist) >= 65 else float(close.iloc[0])
        momentum_3m = round((price_now - ref) / ref, 4)
        rs = round(momentum_3m - market_return, 4)

        # ── 52주(데이터 기간) 고/저점 위치 ───────────────────
        high_period = float(high.max())
        low_period  = float(low.min())
        pos_52w = round((price_now - low_period) / (high_period - low_period), 4) if (high_period - low_period) > 0 else 0.5
        near_52w_high = pos_52w >= 0.75

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
        prior_low         = float(close.iloc[-85:-25].min()) if len(hist) >= 85 else float(close.iloc[0])
        fib_38            = recent_high - (recent_high - prior_low) * 0.382
        fib_62            = recent_high - (recent_high - prior_low) * 0.618
        in_fib_zone       = bool(fib_62 <= price_now <= fib_38)
        is_pullback_range = bool(-0.15 <= pullback_pct <= -0.03)
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
        atr_14     = round(float(tr.rolling(14).mean().iloc[-1]), 0)
        stop_swing = round(price_now - 1.5 * atr_14, 0)   # 스윙 손절 (-1.5 ATR)
        stop_lt    = round(price_now - 2.5 * atr_14, 0)   # 장투 손절 (-2.5 ATR)

        return {
            "price":              price_now,
            "ma5":                round(ma5_v, 0),
            "ma20":               round(ma20_v, 0),
            "ma60":               round(ma60_v, 0),
            "ma120":              round(ma120_v, 0),
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
            "price_above_ma5":    bool(price_above_ma5),
            "ma5_rising":         bool(ma5_rising),
            "no_ma5_break":       bool(no_ma5_break),
            "momentum_3m":        momentum_3m,
            "rs":                 rs,
            "pos_52w":            pos_52w,
            "near_52w_high":      bool(near_52w_high),
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
            "atr_14":             atr_14,
            "stop_swing":         stop_swing,
            "stop_lt":            stop_lt,
        }
    except Exception:
        return None


# ══════════════════════════════════════════════════════
# 스코어링 함수
# ══════════════════════════════════════════════════════

def _score_p1(s: dict) -> float:
    """정배열 퍼지기 직전 + 매집"""
    score = 0.0
    if s["partial_aligned"]:                               score += 20
    if s["ma20_just_cross"]:                               score += 15
    if s["ma60_just_cross"]:                               score += 10
    if s["bb_squeeze"]:                                    score += 20
    if s["obv_rising"]:                                    score += 15
    if s["obv_new_high"]:                                  score += 10
    if s["bullish_ratio"] >= 0.6:                          score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:               score += 10
    if s["rsi"] >= 50:                                     score += 5
    if 1.2 <= s["vol_ratio"] <= 3.0:                       score += 5
    return min(score, 100.0)


def _score_p2(s: dict) -> float:
    """5일선 타고 올라가는 추세 + 거래량 터짐"""
    score = 0.0
    if s["full_aligned"]:                                  score += 20
    if s["price_above_ma5"]:                               score += 10
    if s["ma5_rising"]:                                    score += 10
    if s["no_ma5_break"]:                                  score += 10
    if s["macd"] > 0:                                      score += 10
    if s["macd"] > s["macd_signal"]:                       score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:               score += 5
    if 50 <= s["rsi"] <= 70:                               score += 10
    elif 70 < s["rsi"] <= 80:                              score += 3
    if s["vol_ratio"] >= 2.0:                              score += 10
    if s["vol_ratio"] >= 3.0:                              score += 5
    if s["obv_new_high"]:                                  score += 5
    if s["momentum_3m"] > 0.1:                            score += 5
    return min(score, 100.0)


def _score_p3(s: dict) -> float:
    """눌림목"""
    score = 0.0
    if s["is_pullback_range"]:                             score += 25
    if s["in_fib_zone"]:                                   score += 20
    if s["above_ma20"]:                                    score += 15
    if s["today_bullish"]:                                 score += 10
    if s["partial_aligned"] or s["full_aligned"]:          score += 10
    if s["macd_hist"] > s["macd_hist_prev"] and s["macd_hist"] < 0:  score += 10
    if 35 <= s["rsi"] <= 55:                               score += 10
    return min(score, 100.0)


def _score_canslim(s: dict) -> float:
    """O'Neil CAN SLIM (기술적 요소 — EPS/기관은 추후)"""
    score = 0.0
    # N: 52주 신고가 25% 이내
    if s["pos_52w"] >= 0.85:                               score += 25
    elif s["pos_52w"] >= 0.75:                             score += 15
    # S: 거래량 급증
    if s["vol_ratio"] >= 2.0:                              score += 20
    if s["vol_ratio"] >= 3.0:                              score += 10
    # L: 시장 대비 아웃퍼폼 (RS)
    if s["rs"] > 0.05:                                     score += 15
    if s["rs"] > 0.15:                                     score += 10
    # 정배열 (M 조건)
    if s["full_aligned"]:                                  score += 15
    elif s["partial_aligned"]:                             score += 8
    # RSI 건강
    if 50 <= s["rsi"] <= 75:                               score += 5
    return min(score, 100.0)


def _score_vcp(s: dict) -> float:
    """Minervini VCP (변동성 수축 패턴)"""
    score = 0.0
    # 볼린저 수축 (핵심)
    if s["bb_squeeze"]:                                    score += 30
    # 조정폭 -10~-30% (VCP 범위)
    if -0.30 <= s["pullback_pct"] <= -0.10:                score += 20
    # 거래량 수축 (조용한 조정)
    if s["vol_contracting"]:                               score += 15
    # 정배열 유지
    if s["partial_aligned"]:                               score += 20
    # OBV 방어 (매도세 없음)
    if s["obv_rising"]:                                    score += 15
    return min(score, 100.0)


def _score_stage2(s: dict) -> float:
    """Stan Weinstein Stage 2 (상승 추세 진입)"""
    score = 0.0
    # MA120(200) 위 + 우상향 (핵심)
    if s["price"] > s["ma120"]:                            score += 25
    if s["ma120_rising"]:                                  score += 25
    # MA120 위 유지 기간 (안정적 Stage 2)
    if s["above_ma120_days"] >= 15:                        score += 15
    elif s["above_ma120_days"] >= 8:                       score += 8
    # 정배열
    if s["partial_aligned"]:                               score += 15
    if s["full_aligned"]:                                  score += 5
    # 시장 대비 아웃퍼폼
    if s["rs"] > 0:                                        score += 10
    if s["rs"] > 0.05:                                     score += 5
    return min(score, 100.0)


def _score_wyckoff(s: dict) -> float:
    """Wyckoff 매집 (스마트머니 추적)"""
    score = 0.0
    # OBV 신고점 (스마트머니 매집 핵심 증거)
    if s["obv_new_high"]:                                  score += 35
    elif s["obv_rising"]:                                  score += 20
    # Spring 후 수축 (볼린저 수축)
    if s["bb_squeeze"]:                                    score += 20
    # 양봉 비율 (매수 압력)
    if s["bullish_ratio"] >= 0.65:                         score += 20
    # MA 위 위치
    if s["price"] > s["ma20"]:                             score += 15
    if s["price"] > s["ma60"]:                             score += 10
    return min(score, 100.0)


def _score_darvas(s: dict) -> float:
    """Nicolas Darvas Box (박스권 돌파)"""
    score = 0.0
    # 52주 신고가 근처 (박스 상단 돌파 직후)
    if s["pos_52w"] >= 0.90:                               score += 35
    elif s["pos_52w"] >= 0.80:                             score += 20
    elif s["pos_52w"] >= 0.70:                             score += 10
    # 거래량 폭발
    if s["vol_ratio"] >= 2.0:                              score += 25
    if s["vol_ratio"] >= 3.0:                              score += 15
    # 강한 모멘텀
    if s["momentum_3m"] > 0.15:                            score += 15
    if s["momentum_3m"] > 0.30:                            score += 10
    return min(score, 100.0)


# ══════════════════════════════════════════════════════
# 메인 실행
# ══════════════════════════════════════════════════════

SCORE_THRESHOLD   = 40
ALL_PATTERN_KEYS  = ["p1", "p2", "p3", "canslim", "vcp", "stage2", "wyckoff", "darvas"]
PRO_PATTERN_KEYS  = ["canslim", "vcp", "stage2", "wyckoff", "darvas"]  # 유명 트레이더만
CUSTOM_PATTERN_KEYS = ["p1", "p2", "p3"]                               # 내 3개 패턴

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

BASE_COLS = ["ticker", "name", "market", "sector", "price", "ma5", "ma20", "ma60", "ma120",
             "rsi", "macd", "vol_ratio", "momentum_3m", "rs", "pos_52w", "atr_14", "stop_swing", "stop_lt"]

EXTRA_COLS = {
    "p1":      ["bb_squeeze", "obv_rising", "obv_new_high", "bullish_ratio", "ma20_just_cross"],
    "p2":      ["full_aligned", "no_ma5_break"],
    "p3":      ["pullback_pct", "in_fib_zone", "above_ma20", "today_bullish"],
    "canslim": ["near_52w_high", "rs", "full_aligned"],
    "vcp":     ["bb_squeeze", "vol_contracting", "partial_aligned", "obv_rising", "pullback_pct"],
    "stage2":  ["ma120_rising", "above_ma120_days", "rs"],
    "wyckoff": ["obv_new_high", "obv_rising", "bb_squeeze", "bullish_ratio"],
    "darvas":  ["pos_52w", "near_52w_high", "momentum_3m"],
    "common":  ["pos_52w", "rs", "full_aligned", "obv_rising"],
}


def run(markets=("KOSPI", "KOSDAQ")) -> dict:
    today      = datetime.today()
    start_date = _last_weekday(today - timedelta(days=270))  # 52주(252거래일) 확보

    print("시장 수익률(KOSPI) 계산 중...")
    market_return = _get_market_return(start_date)
    print(f"KOSPI 3M 수익률: {market_return*100:.1f}%")

    frames = []
    for market in markets:
        df = fdr.StockListing(market)
        df["market"] = market
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"Symbol": "ticker", "Code": "ticker", "Name": "name"})
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[df["Marcap"] > 100_000_000_000]
    df = df[df["Close"] > 0]

    # 섹터 컬럼 확보 (있으면 사용, 없으면 빈 문자열)
    sector_col = next((c for c in df.columns if c.lower() in ("sector", "industry", "dept")), None)
    if sector_col:
        df = df.rename(columns={sector_col: "sector"})
    else:
        df["sector"] = ""

    print(f"시가총액 필터 후 종목 수: {len(df)}")

    rows = df[["ticker", "name", "market", "sector"]].to_dict("records")

    def fetch(row):
        s = _get_signals(row["ticker"], start_date, market_return)
        if s is None:
            return None
        scores = {f"score_{k}": fn(s) for k, fn in SCORE_FNS.items()}
        return {**row, **s, **scores}

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            r = future.result()
            if r:
                results.append(r)
            if i % 50 == 0:
                print(f"진행: {i}/{len(rows)}")

    if not results:
        return {k: [] for k in ALL_PATTERN_KEYS + ["common_pro", "common_all"]}

    all_df = pd.DataFrame(results)

    output = {}
    for key in ALL_PATTERN_KEYS:
        col = f"score_{key}"
        extra = [c for c in EXTRA_COLS.get(key, []) if c in all_df.columns]
        output[key] = (
            all_df[all_df[col] >= SCORE_THRESHOLD]
            .nlargest(30, col)
            [BASE_COLS + extra + [col]]
            .rename(columns={col: "score"})
        )

    # ── 공통 1순위: 유명 패턴(5개) 중 3개+ ──────────────────
    pro_hits = sum(
        (all_df[f"score_{k}"] >= SCORE_THRESHOLD).astype(int)
        for k in PRO_PATTERN_KEYS
    )
    all_df["pro_hits"] = pro_hits
    all_df["pro_score"] = sum(
        all_df[f"score_{k}"] for k in PRO_PATTERN_KEYS
    ) / len(PRO_PATTERN_KEYS)

    common_extra = [c for c in EXTRA_COLS["common"] if c in all_df.columns]
    output["common_pro"] = (
        all_df[all_df["pro_hits"] >= 3]
        .nlargest(20, "pro_score")
        [BASE_COLS + common_extra + ["pro_hits", "pro_score"]]
        .rename(columns={"pro_hits": "pattern_hits", "pro_score": "score"})
    )

    # ── 공통 3순위: 내 3개 패턴(P1+P2+P3) 중 2개+ ──────────
    custom_hits = sum(
        (all_df[f"score_{k}"] >= SCORE_THRESHOLD).astype(int)
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
