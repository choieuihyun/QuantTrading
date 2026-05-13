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


def _get_signals(ticker: str, start_date: str) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, start_date)
        if hist.empty or len(hist) < 120:
            return None

        close  = hist["Close"]
        volume = hist["Volume"]
        open_  = hist["Open"]

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

        # ── 5일선 관련 ───────────────────────────────────────
        price_above_ma5 = price_now > ma5_v
        ma5_rising      = float(ma5.iloc[-1]) > float(ma5.iloc[-5])
        no_ma5_break    = bool((close.iloc[-5:] >= ma5.iloc[-5:] * 0.99).all())

        # ── 모멘텀 ───────────────────────────────────────────
        ref = float(close.iloc[-65]) if len(hist) >= 65 else float(close.iloc[0])
        momentum_3m = round((price_now - ref) / ref, 4)

        # ── 정배열 상태 ───────────────────────────────────────
        full_aligned    = ma5_v > ma20_v > ma60_v > ma120_v
        partial_aligned = ma5_v > ma20_v > ma60_v

        # 이평선 막 돌파 여부 (정배열 퍼지기 직전 신호)
        ma20_just_cross = (float(ma20.iloc[-1]) > float(ma60.iloc[-1]) and
                           float(ma20.iloc[-10]) <= float(ma60.iloc[-10]))
        ma60_just_cross = (float(ma60.iloc[-1]) > float(ma120.iloc[-1]) and
                           float(ma60.iloc[-20]) <= float(ma120.iloc[-20]))

        # ── 눌림목 ───────────────────────────────────────────
        recent_high    = float(close.iloc[-25:-3].max())
        pullback_pct   = (price_now - recent_high) / recent_high
        prior_low      = float(close.iloc[-85:-25].min()) if len(hist) >= 85 else float(close.iloc[0])
        fib_38 = recent_high - (recent_high - prior_low) * 0.382
        fib_62 = recent_high - (recent_high - prior_low) * 0.618
        in_fib_zone       = bool(fib_62 <= price_now <= fib_38)
        is_pullback_range = bool(-0.15 <= pullback_pct <= -0.03)
        today_bullish     = float(close.iloc[-1]) > float(open_.iloc[-1])

        # ── 양봉 비율 (매집 판단) ────────────────────────────
        candle_dir    = close.iloc[-20:].values - open_.iloc[-20:].values
        bullish_ratio = float((candle_dir > 0).mean())

        return {
            "price":             price_now,
            "ma5":               round(ma5_v, 0),
            "ma20":              round(ma20_v, 0),
            "ma60":              round(ma60_v, 0),
            "ma120":             round(ma120_v, 0),
            "macd":              round(float(macd_line.iloc[-1]), 4),
            "macd_signal":       round(float(signal_line.iloc[-1]), 4),
            "macd_hist":         round(float(histogram.iloc[-1]), 4),
            "macd_hist_prev":    round(float(histogram.iloc[-2]), 4),
            "rsi":               round(rsi_v, 1),
            "bb_squeeze":        bool(bb_squeeze),
            "obv_rising":        bool(obv_rising),
            "obv_new_high":      bool(obv_new_high),
            "vol_ratio":         vol_ratio,
            "price_above_ma5":   bool(price_above_ma5),
            "ma5_rising":        bool(ma5_rising),
            "no_ma5_break":      bool(no_ma5_break),
            "momentum_3m":       momentum_3m,
            "full_aligned":      bool(full_aligned),
            "partial_aligned":   bool(partial_aligned),
            "ma20_just_cross":   bool(ma20_just_cross),
            "ma60_just_cross":   bool(ma60_just_cross),
            "pullback_pct":      round(pullback_pct, 4),
            "in_fib_zone":       bool(in_fib_zone),
            "is_pullback_range": bool(is_pullback_range),
            "above_ma20":        bool(price_now > ma20_v),
            "today_bullish":     bool(today_bullish),
            "bullish_ratio":     round(bullish_ratio, 2),
        }
    except Exception:
        return None


def _score_p1(s: dict) -> float:
    """정배열 퍼지기 직전 + 매집"""
    score = 0.0
    if s["partial_aligned"]:                                  score += 20
    if s["ma20_just_cross"]:                                  score += 15
    if s["ma60_just_cross"]:                                  score += 10
    if s["bb_squeeze"]:                                       score += 20
    if s["obv_rising"]:                                       score += 15
    if s["obv_new_high"]:                                     score += 10
    if s["bullish_ratio"] >= 0.6:                             score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:                  score += 10
    if s["rsi"] >= 50:                                        score += 5
    if 1.2 <= s["vol_ratio"] <= 3.0:                          score += 5
    return min(score, 100.0)


def _score_p2(s: dict) -> float:
    """5일선 타고 올라가는 추세 + 거래량 터짐"""
    score = 0.0
    if s["full_aligned"]:                                     score += 20
    if s["price_above_ma5"]:                                  score += 10
    if s["ma5_rising"]:                                       score += 10
    if s["no_ma5_break"]:                                     score += 10
    if s["macd"] > 0:                                         score += 10
    if s["macd"] > s["macd_signal"]:                          score += 10
    if s["macd_hist"] > s["macd_hist_prev"]:                  score += 5
    if 50 <= s["rsi"] <= 70:                                  score += 10
    elif 70 < s["rsi"] <= 80:                                 score += 3
    if s["vol_ratio"] >= 2.0:                                 score += 10
    if s["vol_ratio"] >= 3.0:                                 score += 5
    if s["obv_new_high"]:                                     score += 5
    if s["momentum_3m"] > 0.1:                               score += 5
    return min(score, 100.0)


def _score_p3(s: dict) -> float:
    """눌림목"""
    score = 0.0
    if s["is_pullback_range"]:                                score += 25
    if s["in_fib_zone"]:                                      score += 20
    if s["above_ma20"]:                                       score += 15
    if s["today_bullish"]:                                    score += 10
    if s["partial_aligned"] or s["full_aligned"]:             score += 10
    if s["macd_hist"] > s["macd_hist_prev"] and s["macd_hist"] < 0:  score += 10
    if 35 <= s["rsi"] <= 55:                                  score += 10
    return min(score, 100.0)


def run(markets=("KOSPI", "KOSDAQ")) -> dict:
    today      = datetime.today()
    start_date = _last_weekday(today - timedelta(days=200))

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
    print(f"시가총액 필터 후 종목 수: {len(df)}")

    rows = df[["ticker", "name", "market"]].to_dict("records")

    def fetch(row):
        s = _get_signals(row["ticker"], start_date)
        if s is None:
            return None
        return {**row, **s, "score_p1": _score_p1(s), "score_p2": _score_p2(s), "score_p3": _score_p3(s)}

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
        return {"p1": [], "p2": [], "p3": []}

    all_df = pd.DataFrame(results)

    BASE = ["ticker", "name", "market", "price", "ma5", "ma20", "ma60", "ma120",
            "rsi", "macd", "vol_ratio", "momentum_3m"]

    p1 = (all_df[all_df["score_p1"] >= 40]
          .nlargest(30, "score_p1")
          [BASE + ["bb_squeeze", "obv_rising", "obv_new_high", "bullish_ratio", "ma20_just_cross", "score_p1"]]
          .rename(columns={"score_p1": "score"}))

    p2 = (all_df[all_df["score_p2"] >= 40]
          .nlargest(30, "score_p2")
          [BASE + ["full_aligned", "no_ma5_break", "score_p2"]]
          .rename(columns={"score_p2": "score"}))

    p3 = (all_df[all_df["score_p3"] >= 40]
          .nlargest(30, "score_p3")
          [BASE + ["pullback_pct", "in_fib_zone", "above_ma20", "today_bullish", "score_p3"]]
          .rename(columns={"score_p3": "score"}))

    return {"p1": p1, "p2": p2, "p3": p3}
