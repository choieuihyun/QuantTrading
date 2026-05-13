import pandas as pd
import FinanceDataReader as fdr
from datetime import datetime, timedelta


def _last_weekday(dt: datetime) -> str:
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _get_momentum(ticker: str, date_3m: str) -> float | None:
    try:
        hist = fdr.DataReader(ticker, date_3m)
        if hist.empty or len(hist) < 2:
            return None
        price_3m = hist.iloc[0]["Close"]
        price_now = hist.iloc[-1]["Close"]
        if price_3m <= 0:
            return None
        return round((price_now - price_3m) / price_3m, 4)
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

    # 중복 컬럼 제거 (rename으로 인한 경우)
    df = df.loc[:, ~df.columns.duplicated()]

    df = df[df["PER"].notna() & df["PBR"].notna()]
    df = df[df["PER"] > 0]
    df = df[df["PBR"] > 0]
    df = df[df["PER"].between(5, 20)]
    df = df[df["PBR"].between(0.5, 2.0)]

    print(f"PER/PBR 필터 후 종목 수: {len(df)}")

    df["momentum_3m"] = df["ticker"].apply(lambda t: _get_momentum(t, date_3m))
    df = df.dropna(subset=["momentum_3m"])
    df = df[df["momentum_3m"] > 0.05]

    df["score"] = (
        (1 - (df["PER"] - 5) / 15) * 30
        + (1 - (df["PBR"] - 0.5) / 1.5) * 20
        + df["momentum_3m"].clip(upper=0.35) / 0.35 * 50
    ).round(2)

    df = df.nlargest(50, "score")

    price_col = "Close" if "Close" in df.columns else "Adj Close"
    return df[["ticker", "name", "market", price_col, "PER", "PBR", "momentum_3m", "score"]].rename(
        columns={price_col: "price"}
    )
