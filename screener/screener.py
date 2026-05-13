import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta


def _last_weekday(dt: datetime) -> str:
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _get_signals(ticker: str, date_3m: str) -> dict | None:
    try:
        hist = fdr.DataReader(ticker, date_3m)
        if hist.empty or len(hist) < 20:
            return None

        price_3m = hist.iloc[0]["Close"]
        price_now = hist.iloc[-1]["Close"]
        if price_3m <= 0:
            return None

        momentum_3m = round((price_now - price_3m) / price_3m, 4)

        vol_avg_20 = hist["Volume"].iloc[-20:].mean()
        vol_today = hist["Volume"].iloc[-1]
        vol_ratio = round(vol_today / vol_avg_20, 2) if vol_avg_20 > 0 else None

        return {"momentum_3m": momentum_3m, "vol_ratio": vol_ratio, "price": price_now}
    except Exception:
        return None


def run(markets=("KOSPI", "KOSDAQ")) -> pd.DataFrame:
    today = datetime.today()
    date_3m = _last_weekday(today - timedelta(days=90))

    frames = []
    for market in markets:
        df = fdr.StockListing(market)
        df["market"] = market
        frames.append(df)

    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"Symbol": "ticker", "Code": "ticker", "Name": "name"})
    df = df.loc[:, ~df.columns.duplicated()]

    # 시가총액 1000억 이상만 (종목 수 줄여서 속도 확보)
    df = df[df["Marcap"] > 100_000_000_000]
    df = df[df["Close"] > 0]
    print(f"시가총액 필터 후 종목 수: {len(df)}")

    results = []
    for _, row in df.iterrows():
        signals = _get_signals(row["ticker"], date_3m)
        if signals is None:
            continue
        results.append({
            "ticker": row["ticker"],
            "name": row["name"],
            "market": row["market"],
            "price": signals["price"],
            "momentum_3m": signals["momentum_3m"],
            "vol_ratio": signals["vol_ratio"],
        })

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)
    result_df = result_df[result_df["momentum_3m"] > 0.05]
    result_df = result_df[result_df["vol_ratio"].notna()]

    result_df["score"] = (
        result_df["momentum_3m"].clip(upper=0.50) / 0.50 * 70
        + (result_df["vol_ratio"].clip(upper=3.0) - 1).clip(lower=0) / 2.0 * 30
    ).round(2)

    return result_df.nlargest(50, "score")[
        ["ticker", "name", "market", "price", "momentum_3m", "vol_ratio", "score"]
    ]
