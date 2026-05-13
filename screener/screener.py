import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


def _last_weekday(dt: datetime) -> str:
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _get_signals(ticker: str, date_6m: str) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, date_6m)
        if hist.empty or len(hist) < 60:
            return None

        close = hist["Close"]
        price_now = close.iloc[-1]
        price_3m_ago = close.iloc[-65] if len(hist) >= 65 else close.iloc[0]

        if price_now <= 0 or price_3m_ago <= 0:
            return None

        # 이동평균
        ma5  = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()

        ma5_now  = ma5.iloc[-1]
        ma20_now = ma20.iloc[-1]
        ma60_now = ma60.iloc[-1]

        # 정배열 여부 (MA5 > MA20 > MA60)
        is_aligned = bool(ma5_now > ma20_now > ma60_now)

        # 5일선 지지: 현재가 MA5 위 + MA5 우상향
        price_above_ma5 = bool(price_now > ma5_now)
        ma5_rising = bool(ma5.iloc[-1] > ma5.iloc[-5])

        # 5일선 이탈 여부: 최근 5거래일 중 종가가 MA5 아래로 꺾인 날 없는지
        recent_close = close.iloc[-5:]
        recent_ma5   = ma5.iloc[-5:]
        no_ma5_break = bool((recent_close >= recent_ma5).all())

        # 3개월 모멘텀
        momentum_3m = round((price_now - price_3m_ago) / price_3m_ago, 4)

        # 거래량 증가율 (오늘 vs 20일 평균)
        vol_avg_20 = hist["Volume"].iloc[-20:].mean()
        vol_today  = hist["Volume"].iloc[-1]
        vol_ratio  = round(vol_today / vol_avg_20, 2) if vol_avg_20 > 0 else None

        return {
            "price":          price_now,
            "momentum_3m":    momentum_3m,
            "vol_ratio":      vol_ratio,
            "is_aligned":     is_aligned,
            "price_above_ma5": price_above_ma5,
            "ma5_rising":     ma5_rising,
            "no_ma5_break":   no_ma5_break,
            "ma5":  round(ma5_now, 0),
            "ma20": round(ma20_now, 0),
            "ma60": round(ma60_now, 0),
        }
    except Exception:
        return None


def run(markets=("KOSPI", "KOSDAQ")) -> pd.DataFrame:
    today = datetime.today()
    date_6m = _last_weekday(today - timedelta(days=180))

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
        signals = _get_signals(row["ticker"], date_6m)
        if signals is None:
            return None
        return {**row, **signals}

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch, row): row for row in rows}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                results.append(result)
            if i % 50 == 0:
                print(f"진행: {i}/{len(rows)}")

    if not results:
        return pd.DataFrame()

    df = pd.DataFrame(results)

    # 필터: 정배열 + 5일선 지지 + 이탈 없음 + 모멘텀 5%+
    df = df[df["is_aligned"]]
    df = df[df["price_above_ma5"]]
    df = df[df["ma5_rising"]]
    df = df[df["no_ma5_break"]]
    df = df[df["momentum_3m"] > 0.05]
    df = df[df["vol_ratio"].notna()]

    # 점수: 모멘텀 50% + 거래량 30% + MA 정배열 벌어짐 정도 20%
    df["ma_gap"] = (df["ma5"] - df["ma60"]) / df["ma60"]
    df["score"] = (
        df["momentum_3m"].clip(upper=0.50) / 0.50 * 50
        + (df["vol_ratio"].clip(upper=3.0) - 1).clip(lower=0) / 2.0 * 30
        + df["ma_gap"].clip(upper=0.10) / 0.10 * 20
    ).round(2)

    return df.nlargest(50, "score")[
        ["ticker", "name", "market", "price", "ma5", "ma20", "ma60",
         "momentum_3m", "vol_ratio", "is_aligned", "no_ma5_break", "score"]
    ]
