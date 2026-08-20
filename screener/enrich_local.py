"""
KRX 수급·공매도·밸류에이션 보강 — 로컬 전용.

KRX가 데이터센터 IP를 Akamai 엣지에서 막아 GitHub Actions에서는 어떤 자격증명으로도
접속되지 않는다. 막히지 않은 환경은 개인 PC뿐이라 이 경로를 따로 둔다.

전 종목 대량 조회가 되므로 종목당 호출이 아니라 시장당 몇 번으로 끝난다
(2,700종목 기준 약 20회). 주 1회만 돌려도 컬럼은 채워진다.

  python enrich_local.py              # KOSPI+KOSDAQ 수집 후 Firestore 업로드
  python enrich_local.py --dry-run    # 업로드 없이 결과만 확인

KRX_ID/KRX_PW는 screener/.env 에서 읽는다.
Firebase는 screener/serviceAccount.json (콘솔에서 받은 키 파일)을 쓴다.
"""

import argparse
import os
from datetime import datetime, timedelta

import pandas as pd

MARKETS = {"KOSPI": "kr", "KOSDAQ": "kr"}
# 단기(1개월)와 중기(3개월). O'Neil은 기관이 여러 분기에 걸쳐 늘리는 것을 본다.
WINDOWS = {"20d": 20, "60d": 60}
INVESTORS = {"foreign": "외국인", "inst": "기관합계"}
SHORT_SAMPLE_DAYS = 5     # 공매도 거래비중은 하루치가 튀어 며칠 평균을 쓴다

# (원본 컬럼, 저장 키, 소수 자리). 저장 키가 짧은 이유는 키 이름이 종목 수만큼 반복돼
# 문서 용량의 절반 이상을 먹기 때문이다 — 실측 978KB 중 609KB가 키 이름이었다.
# 뜻은 flows 문서의 legend에 함께 저장한다.
FIELD_MAP = [
    ("foreign_net_20d_pct", "f20", 2),
    ("inst_net_20d_pct",    "i20", 2),
    ("foreign_net_60d_pct", "f60", 2),
    ("inst_net_60d_pct",    "i60", 2),
    ("short_vol_pct",       "sv",  2),
    ("short_bal_pct",       "sb",  2),
    ("per",                 "per", 1),
    ("pbr",                 "pbr", 2),
    ("div_yield",           "div", 2),
    ("eps",                 "eps", 0),
]
LEGEND = {
    "f20": "외국인 20일 순매수 / 시가총액 (%)",
    "i20": "기관 20일 순매수 / 시가총액 (%)",
    "f60": "외국인 60일 순매수 / 시가총액 (%)",
    "i60": "기관 60일 순매수 / 시가총액 (%)",
    "sv":  "공매도 거래비중 5일 평균 (%)",
    "sb":  "공매도 잔고비중 — 상장주식수 대비 (%)",
    "per": "PER (KRX 공식)", "pbr": "PBR", "div": "배당수익률 (%)", "eps": "EPS",
}
LOOKBACK_DAYS = 10        # 휴장·지연공시를 거슬러 올라가는 한도

# 백분위를 종목마다 저장하면 문서가 두 배가 된다. 분포(0~100 분위 경계값)를 한 번만
# 저장하고 화면에서 위치를 찾게 한다 — 6개 지표 × 101개 = 606개 숫자면 끝난다.
DIST_KEYS = ["f20", "i20", "f60", "i60", "sv", "sb"]


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


def _ymd(d):
    return d.strftime("%Y%m%d")


def _recent(fn, label: str):
    """지연 공시·휴장일을 거슬러 올라가며 데이터가 있는 첫 날을 찾는다.
    공매도 잔고는 며칠 늦게 공시돼 오늘 날짜로 부르면 항상 빈 결과다."""
    day = datetime.today()
    for _ in range(LOOKBACK_DAYS):
        try:
            df = fn(_ymd(day))
            if df is not None and not df.empty:
                return df, day.date().isoformat()
        except Exception:
            pass
        day -= timedelta(days=1)
    print(f"    ✗ {label}: 최근 {LOOKBACK_DAYS}일 안에 데이터 없음")
    return None, None


def collect(market: str) -> pd.DataFrame:
    from pykrx import stock

    end = datetime.today()
    out = {}

    # ── 투자자별 순매수 (기간 누적) ─────────────────────
    for wkey, wdays in WINDOWS.items():
        start = end - timedelta(days=int(wdays * 1.6) + 5)
        for ikey, iname in INVESTORS.items():
            try:
                df = stock.get_market_net_purchases_of_equities(
                    _ymd(start), _ymd(end), market, iname)
            except Exception as e:
                print(f"    ✗ {iname} {wkey}: {type(e).__name__} {str(e)[:50]}")
                continue
            if df is None or df.empty or "순매수거래대금" not in df.columns:
                print(f"    ✗ {iname} {wkey}: 빈 결과")
                continue
            s = pd.to_numeric(df["순매수거래대금"], errors="coerce")
            s.index = df.index.astype(str).str.zfill(6)
            out[f"{ikey}_net_{wkey}"] = s[~s.index.duplicated()]
            print(f"    ✓ {iname} {wkey}: {len(s):,}종목")

    # ── 시가총액 (순매수 정규화에 필요) ──────────────────
    cap, cap_date = _recent(lambda d: stock.get_market_cap_by_ticker(d, market), "시가총액")
    if cap is not None and "시가총액" in cap.columns:
        s = pd.to_numeric(cap["시가총액"], errors="coerce")
        s.index = cap.index.astype(str).str.zfill(6)
        out["marcap"] = s[~s.index.duplicated()]
        print(f"    ✓ 시가총액: {len(s):,}종목 ({cap_date})")

    # ── 공매도 거래비중 (며칠 평균) ─────────────────────
    day, got = end, []
    for _ in range(LOOKBACK_DAYS + SHORT_SAMPLE_DAYS):
        if len(got) >= SHORT_SAMPLE_DAYS:
            break
        try:
            df = stock.get_shorting_volume_by_ticker(_ymd(day), market)
            if df is not None and not df.empty and "비중" in df.columns:
                s = pd.to_numeric(df["비중"], errors="coerce")
                s.index = df.index.astype(str).str.zfill(6)
                got.append(s[~s.index.duplicated()])
        except Exception:
            pass
        day -= timedelta(days=1)
    if got:
        out["short_vol_pct"] = pd.concat(got, axis=1).mean(axis=1)
        print(f"    ✓ 공매도 거래비중: {len(out['short_vol_pct']):,}종목 ({len(got)}일 평균)")

    # ── 공매도 잔고비중 (지연 공시 — 거슬러 올라간다) ────
    bal, bal_date = _recent(lambda d: stock.get_shorting_balance_by_ticker(d, market), "공매도 잔고")
    if bal is not None and "비중" in bal.columns:
        s = pd.to_numeric(bal["비중"], errors="coerce")
        s.index = bal.index.astype(str).str.zfill(6)
        out["short_bal_pct"] = s[~s.index.duplicated()]
        print(f"    ✓ 공매도 잔고비중: {len(s):,}종목 ({bal_date})")

    # ── KRX 공식 밸류에이션 ─────────────────────────────
    val, val_date = _recent(lambda d: stock.get_market_fundamental_by_ticker(d, market), "PER/PBR")
    if val is not None:
        idx = val.index.astype(str).str.zfill(6)
        for col, key in [("PER", "per"), ("PBR", "pbr"), ("DIV", "div_yield"), ("EPS", "eps")]:
            if col in val.columns:
                s = pd.to_numeric(val[col], errors="coerce")
                s.index = idx
                # 미상장·관리종목은 0으로 오는데 그대로 두면 "PER 0 = 초저평가"로 읽힌다
                out[key] = s[~s.index.duplicated()].replace(0, pd.NA)
        print(f"    ✓ PER/PBR/EPS/배당: {len(idx):,}종목 ({val_date})")

    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    df.index.name = "ticker"

    # 원화 절대액은 대형주가 항상 이긴다. 시총 대비 비율이라야 종목 간 비교가 된다.
    if "marcap" in df.columns:
        cap = df["marcap"].where(df["marcap"] > 0)
        for c in [c for c in df.columns if c.endswith(("_20d", "_60d"))]:
            df[f"{c}_pct"] = (df[c] / cap * 100).round(4)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="업로드 없이 결과만 출력")
    a = ap.parse_args()

    load_env()
    from investor_flow import check_login
    ok, why = check_login()
    print(f"KRX 로그인: {'성공' if ok else '실패'} — {why}")
    if not ok:
        raise SystemExit(1)

    frames = []
    for market in MARKETS:
        print(f"\n[{market}]")
        df = collect(market)
        if not df.empty:
            frames.append(df)
    if not frames:
        raise SystemExit("수집 결과가 없습니다")

    all_df = pd.concat(frames)
    all_df = all_df[~all_df.index.duplicated()]
    print(f"\n합계 {len(all_df):,}종목 · 컬럼 {len(all_df.columns)}개")

    show = [c for c in ("foreign_net_20d_pct", "inst_net_20d_pct",
                        "short_bal_pct", "short_vol_pct", "per", "pbr") if c in all_df]
    # PER 0을 pd.NA로 치환해서 astype(float)가 죽는다. NA를 견디는 변환을 쓴다.
    num = all_df[show].apply(pd.to_numeric, errors="coerce")
    print(num.describe().T[["count", "mean", "50%", "max"]].round(2).to_string())

    if "foreign_net_20d_pct" in num:
        print("\n외국인 20일 순매수 상위 (시총 대비)")
        print(num.nlargest(5, "foreign_net_20d_pct").round(2).to_string())

    payload = {}
    for tk, row in all_df.iterrows():
        rec = {}
        for src, dst, nd in FIELD_MAP:
            v = row.get(src)
            if v is None or pd.isna(v):
                continue                      # 없는 값은 키 자체를 생략
            rec[dst] = int(v) if nd == 0 else round(float(v), nd)
        if rec:
            payload[str(tk)] = rec

    # 유니버스 분포 — "외국인 +1.2%"가 큰 값인지 화면에서 판단할 수 있게 한다.
    # 공매도 잔고는 중앙값 0.17%에 최대 10.57%라 절대값만으로는 감이 안 온다.
    import numpy as np
    dist = {}
    for k in DIST_KEYS:
        vals = [r[k] for r in payload.values() if k in r]
        if len(vals) >= 100:
            dist[k] = [round(float(x), 4) for x in np.percentile(vals, range(101))]

    import json
    size = len(json.dumps(payload).encode()) / 1024
    print(f"\n문서 크기 {size:.0f} KB (Firestore 한도 1024) · 분포 {len(dist)}개 지표")
    for k in DIST_KEYS:
        if k in dist:
            print(f"   {k:4} 하위10% {dist[k][10]:8.2f} · 중앙 {dist[k][50]:8.2f} · 상위10% {dist[k][90]:8.2f}")
    if size > 900:
        raise SystemExit(f"문서가 너무 큽니다 ({size:.0f}KB) — 한도를 넘으면 쓰기가 통째로 거부됩니다")

    if a.dry_run:
        print("--dry-run — 업로드하지 않았습니다")
        return

    import firebase_upload
    firebase_upload.save_flows("kr", payload, LEGEND, dist,
                               datetime.today().strftime("%Y-%m-%d"))


if __name__ == "__main__":
    main()
