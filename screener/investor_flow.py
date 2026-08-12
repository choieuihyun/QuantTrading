"""
외국인·기관 순매수 — CAN SLIM의 I(기관 수급). 한국 전용.

가격·거래량에서 파생되지 않은 유일한 독립 축이다. 나머지 지표는 전부 OHLCV에서
나오므로 서로 상관이 높지만, 누가 샀는지는 다른 데이터다.

KRX가 투자자별 데이터에 로그인을 요구한다. KRX_ID/KRX_PW 환경변수가 없으면
조용히 빈 결과를 반환한다 — 이 값이 없다고 스크리닝 전체가 죽으면 안 된다.

측정 방식: 기간 순매수 거래대금을 시가총액으로 나눈 비율을 쓴다. 원화 절대액은
대형주가 항상 이기므로 종목 간 비교가 불가능하다.
"""

import os
from datetime import datetime, timedelta

import pandas as pd

# 단기(1개월)와 중기(3개월). O'Neil은 기관이 '여러 분기에 걸쳐' 늘리는 것을 본다.
WINDOWS = {"20d": 20, "60d": 60}
MARKETS = ["KOSPI", "KOSDAQ"]
INVESTORS = {"foreign": "외국인", "inst": "기관합계"}

# 컬럼명이 pykrx 버전에 따라 흔들려 후보를 둔다
VALUE_COLS = ["순매수거래대금", "순매수금액", "거래대금"]


def available() -> bool:
    return bool(os.getenv("KRX_ID") and os.getenv("KRX_PW"))


def _net_value(stock, start: str, end: str, market: str, investor: str) -> pd.Series | None:
    """티커별 순매수 거래대금. 실패하면 None — 부분 실패가 전체를 죽이지 않게 한다."""
    try:
        df = stock.get_market_net_purchases_of_equities(start, end, market, investor)
    except Exception as e:
        print(f"    {market}/{investor} 조회 실패: {type(e).__name__} {e}")
        return None
    if df is None or df.empty:
        return None
    col = next((c for c in VALUE_COLS if c in df.columns), None)
    if col is None:
        print(f"    {market}/{investor}: 순매수 컬럼 없음 — 받은 컬럼 {list(df.columns)}")
        return None
    s = pd.to_numeric(df[col], errors="coerce")
    s.index = df.index.astype(str).str.zfill(6)
    return s[~s.index.duplicated()]


def fetch(days_back: int = 90) -> pd.DataFrame:
    """
    반환: ticker를 인덱스로 하는 DataFrame.
      foreign_net_20d / inst_net_20d / foreign_net_60d / inst_net_60d  (원)

    시가총액 대비 비율 변환은 marcap을 아는 호출부(attach)에서 한다.
    """
    if not available():
        print("외인·기관 수급: KRX_ID/KRX_PW 미설정 — 건너뜀")
        return pd.DataFrame()

    from pykrx import stock  # 자격증명이 있을 때만 임포트 (없으면 임포트 시점에 실패 로그)

    end = datetime.today()
    fmt = lambda d: d.strftime("%Y%m%d")
    out = {}

    for wkey, wdays in WINDOWS.items():
        # 달력일 기준으로 넉넉히 잡는다 — 거래일 수를 정확히 셀 필요는 없다
        start = end - timedelta(days=int(wdays * 1.6) + 5)
        for ikey, iname in INVESTORS.items():
            parts = [s for m in MARKETS
                     if (s := _net_value(stock, fmt(start), fmt(end), m, iname)) is not None]
            if parts:
                out[f"{ikey}_net_{wkey}"] = pd.concat(parts)
                print(f"  {iname} {wkey}: {len(out[f'{ikey}_net_{wkey}']):,}종목")

    if not out:
        print("외인·기관 수급: 조회 결과 없음 — 로그인 실패 또는 API 변경")
        return pd.DataFrame()

    df = pd.DataFrame(out)
    df.index.name = "ticker"
    return df


def attach(results: dict, flows: pd.DataFrame) -> dict:
    """
    패턴별 결과 DataFrame에 수급 컬럼을 붙인다.

    원화 절대액은 대형주가 항상 이기므로 시총 대비 비율(%)을 함께 만든다.
    점수에는 넣지 않는다 — 겹치면 낫다는 가정이 실측에서 무너진 전례가 있어,
    표시 컬럼으로 쌓아 실측한 뒤에 게이트를 논한다.
    """
    if flows.empty:
        return results

    for key, df in results.items():
        if not hasattr(df, "empty") or df.empty or "ticker" not in df.columns:
            continue
        merged = df.merge(flows, left_on="ticker", right_index=True, how="left")
        if "marcap" in merged.columns:
            cap = pd.to_numeric(merged["marcap"], errors="coerce")
            for c in flows.columns:
                merged[f"{c}_pct"] = (merged[c] / cap.where(cap > 0)).round(6)
        results[key] = merged
    return results


if __name__ == "__main__":
    # 자격증명 확인용: python investor_flow.py
    # 로컬에서는 screener/.env 에 KRX_ID/KRX_PW를 넣어두면 읽는다 (.env는 gitignore 처리됨)
    env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env):
        for line in open(env, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))

    if not available():
        raise SystemExit("KRX_ID/KRX_PW가 없습니다. screener/.env 에 넣거나 export 하세요.")

    df = fetch()
    if df.empty:
        raise SystemExit("조회 실패 — 위 로그의 오류를 확인하세요.")
    print(f"\n수집 {len(df):,}종목 · 컬럼 {list(df.columns)}")
    print(df.describe().T[["count", "mean", "min", "max"]])
    print("\n상위 5 (외인 20일 순매수액):")
    print(df.nlargest(5, "foreign_net_20d")[["foreign_net_20d", "inst_net_20d"]])
