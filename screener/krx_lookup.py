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

# 실측 컬럼명 — "외국인"이 아니라 "외국인합계"다. 개인은 잔차라 따로 안 본다.
INVESTORS = ["외국인합계", "기관합계"]


def drop_incomplete(df, cols):
    """장중이면 당일 행이 전부 0으로 온다. 그대로 평균에 넣으면 조용히 값이 깎인다."""
    if df is None or df.empty:
        return df
    have = [c for c in cols if c in df.columns]
    if not have:
        return df
    zero = (df[have].fillna(0) == 0).all(axis=1)
    return df[~zero]


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
    cap = data.get("시가총액")
    marcap = float(cap["시가총액"].iloc[-1]) if cap is not None and "시가총액" in cap else None

    inv = drop_incomplete(data.get("투자자별 거래대금"), INVESTORS)
    if inv is not None and len(inv):
        cols = [c for c in INVESTORS if c in inv.columns]
        print(f"\n■ 순매수 거래대금 누적 ({len(inv)}거래일)")
        for c in cols:
            v = pd.to_numeric(inv[c], errors="coerce").sum()
            # 원화 절대액은 대형주가 항상 이긴다. 시총 대비 비율이라야 종목 간 비교가 된다.
            pct = f" ({v / marcap * 100:+.2f}% of 시총)" if marcap else ""
            print(f"   {c:10} {v/1e8:+12,.1f}억{pct}")
        print("\n   최근 5일 (억원)")
        print(inv[cols].tail(5).apply(lambda s: (s / 1e8).round(0)).to_string())

    sh = drop_incomplete(data.get("공매도 거래"), ["공매도", "매수"])
    if sh is not None and len(sh) and "비중" in sh.columns:
        w = pd.to_numeric(sh["비중"], errors="coerce")
        print(f"\n■ 공매도 거래비중 — 평균 {w.mean():.2f}% · 최근 {w.iloc[-1]:.2f}% · 최고 {w.max():.2f}%")

    bal = data.get("공매도 잔고")
    if bal is not None and len(bal) and "비중" in bal.columns:
        w = pd.to_numeric(bal["비중"], errors="coerce")
        arrow = "↑" if len(w) > 1 and w.iloc[-1] > w.iloc[0] else "↓"
        print(f"■ 공매도 잔고비중 — 최근 {w.iloc[-1]:.2f}% ({w.iloc[0]:.2f}% → {w.iloc[-1]:.2f}% {arrow})")

    val = drop_incomplete(data.get("PER/PBR/배당"), ["PER", "PBR", "EPS"])
    if val is not None and len(val):
        r = val.iloc[-1]
        print(f"■ PER {r.get('PER')} · PBR {r.get('PBR')} · EPS {r.get('EPS'):,} · 배당수익률 {r.get('DIV')}%")


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
