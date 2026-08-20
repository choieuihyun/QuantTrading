"""
종목 하나의 외인·기관 수급 / 공매도를 필요할 때만 조회한다. 로컬 전용.

KRX가 데이터센터 IP를 막아 GitHub Actions에서는 어떤 자격증명으로도 안 된다.
이 스크립트는 네 PC에서 돌리는 용도다 — 종목 하나씩이라 요청량도 미미하다.

  python krx_lookup.py 005930
  python krx_lookup.py 삼성전자 --days 60
  python krx_lookup.py 005930 --raw      # 응답 원형 그대로 (컬럼 확인용)

자격증명은 screener/.env 의 KRX_ID/KRX_PW를 읽거나, 없으면 직접 물어본다.
"""

import argparse
import os
from datetime import datetime, timedelta

import pandas as pd

from investor_flow import check_login

# 수급을 볼 때 궁금한 건 "누가 얼마나 샀나"다. 개인은 잔차라 따로 안 본다.
INVESTORS = ["외국인", "기관합계"]


def load_env():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    if not (os.getenv("KRX_ID") and os.getenv("KRX_PW")):
        import getpass
        os.environ["KRX_ID"] = input("KRX 아이디: ").strip()
        os.environ["KRX_PW"] = getpass.getpass("KRX 비밀번호(화면에 안 보임): ")


def resolve(name_or_code: str) -> tuple[str, str]:
    """종목명으로도 찾을 수 있게. 미러 리스트를 쓰므로 KRX를 안 거친다."""
    import screener
    df = pd.concat([screener.krx_listing(m) for m in ("KOSPI", "KOSDAQ")], ignore_index=True)
    s = str(name_or_code).strip()
    hit = df[df["Code"].astype(str) == s]
    if hit.empty:
        hit = df[df["Name"].astype(str).str.contains(s, case=False, na=False)]
    if hit.empty:
        raise SystemExit(f"'{s}' 종목을 찾지 못했습니다")
    if len(hit) > 1:
        print(f"'{s}' 후보 {len(hit)}개 — 첫 번째를 씁니다: "
              + ", ".join(f"{r.Name}({r.Code})" for r in hit.head(5).itertuples()))
    return str(hit["Code"].iloc[0]), str(hit["Name"].iloc[0])


def fetch(code: str, days: int, raw: bool) -> dict:
    from pykrx import stock
    end = datetime.today()
    start = end - timedelta(days=days)
    f = lambda d: d.strftime("%Y%m%d")
    out = {}

    calls = {
        "투자자별 거래대금": lambda: stock.get_market_trading_value_by_date(f(start), f(end), code),
        "공매도 거래":      lambda: stock.get_shorting_volume_by_date(f(start), f(end), code),
        "공매도 잔고":      lambda: stock.get_shorting_balance_by_date(f(start), f(end), code),
        "시가총액":         lambda: stock.get_market_cap_by_date(f(start), f(end), code),
        "PER/PBR/배당":     lambda: stock.get_market_fundamental(f(start), f(end), code),
    }
    for label, fn in calls.items():
        try:
            df = fn()
        except Exception as e:
            print(f"  ✗ {label}: {type(e).__name__} {str(e)[:80]}")
            continue
        if df is None or df.empty:
            print(f"  ✗ {label}: 빈 결과")
            continue
        print(f"  ✓ {label}: {df.shape[0]}행 · 컬럼 {list(df.columns)}")
        out[label] = df
        if raw:
            print(df.tail(3).to_string(), "\n")
    return out


def summarize(data: dict, name: str, code: str, price: float | None):
    inv = data.get("투자자별 거래대금")
    if inv is not None:
        cols = [c for c in INVESTORS if c in inv.columns]
        if cols:
            print(f"\n■ 순매수 거래대금 누적 ({len(inv)}거래일)")
            for c in cols:
                v = pd.to_numeric(inv[c], errors="coerce").sum()
                print(f"   {c:8} {v/1e8:+12,.1f}억")
            print(f"\n   최근 5일")
            print(inv[cols].tail(5).apply(lambda s: (s / 1e8).round(1)).to_string())

    sh = data.get("공매도 거래")
    if sh is not None:
        vol = next((c for c in ("공매도", "공매도거래량") if c in sh.columns), None)
        tot = next((c for c in ("거래량", "총거래량") if c in sh.columns), None)
        if vol and tot:
            a = pd.to_numeric(sh[vol], errors="coerce").sum()
            b = pd.to_numeric(sh[tot], errors="coerce").sum()
            print(f"\n■ 공매도 비중 {a/b*100:.2f}%  (공매도 {a:,.0f} / 전체 {b:,.0f})")

    bal = data.get("공매도 잔고")
    if bal is not None and len(bal):
        print(f"\n■ 공매도 잔고 최근")
        print(bal.tail(3).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="종목코드 또는 종목명")
    ap.add_argument("--days", type=int, default=30, help="조회 기간(달력일)")
    ap.add_argument("--raw", action="store_true", help="응답 원형 출력")
    a = ap.parse_args()

    load_env()
    ok, why = check_login()
    print(f"KRX 로그인: {'성공' if ok else '실패'} — {why}")
    if not ok:
        raise SystemExit(1)

    code, name = resolve(a.target)
    print(f"\n=== {name} ({code}) · 최근 {a.days}일 ===")
    data = fetch(code, a.days, a.raw)
    if not data:
        raise SystemExit("조회된 데이터가 없습니다 — 위 실패 사유를 확인하세요")
    summarize(data, name, code, None)


if __name__ == "__main__":
    main()
