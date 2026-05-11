import pandas as pd
from pykrx import stock
from datetime import datetime, timedelta


def _last_weekday(dt: datetime) -> str:
    while dt.weekday() >= 5:
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d")


def run(markets=("KOSPI", "KOSDAQ")) -> pd.DataFrame:
    today = datetime.today()
    date_now = _last_weekday(today)
    date_3m = _last_weekday(today - timedelta(days=90))

    frames = []
    for market in markets:
        df_fund = stock.get_market_fundamental(date_now, market=market)
        df_now = stock.get_market_ohlcv(date_now, market=market)
        df_3m = stock.get_market_ohlcv(date_3m, market=market)

        df = df_fund[["PER", "PBR"]].copy()
        df["price"] = df_now["종가"]
        df["price_3m"] = df_3m["종가"]
        df["market"] = market
        frames.append(df)

    df = pd.concat(frames)
    df.index.name = "ticker"

    df = df[(df["PER"] > 0) & (df["PBR"] > 0) & (df["price"] > 0) & (df["price_3m"] > 0)]

    df["momentum_3m"] = ((df["price"] - df["price_3m"]) / df["price_3m"]).round(4)

    df = df[df["PER"].between(5, 20)]
    df = df[df["PBR"].between(0.5, 2.0)]
    df = df[df["momentum_3m"] > 0.05]

    df["score"] = (
        (1 - (df["PER"] - 5) / 15) * 30
        + (1 - (df["PBR"] - 0.5) / 1.5) * 20
        + df["momentum_3m"].clip(upper=0.35) / 0.35 * 50
    ).round(2)

    df = df.nlargest(50, "score").reset_index()
    df["name"] = df["ticker"].map(stock.get_market_ticker_name)

    return df[["ticker", "name", "market", "price", "PER", "PBR", "momentum_3m", "score"]]
