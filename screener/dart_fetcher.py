import os
import pandas as pd
import OpenDartReader as ODR
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


def _client():
    return ODR(os.environ["DART_API_KEY"])


def _parse_amount(val) -> int | None:
    if pd.isna(val) if not isinstance(val, str) else not val:
        return None
    try:
        return int(str(val).replace(",", "").replace(" ", "").replace("△", "-"))
    except Exception:
        return None


def _fetch_one(dart, ticker: str) -> dict:
    base = {"ticker": ticker, "eps_current": None, "eps_prev_year": None,
            "eps_yoy": None, "rev_yoy": None, "canslim_c": False}
    try:
        corp = dart.company(ticker)
        if not corp or "corp_code" not in corp:
            return base
        corp_code = corp["corp_code"]

        year = datetime.today().year
        # 가장 최근 보고서부터 시도 (3Q → 반기 → 1Q → 연간)
        for reprt_code in ["11014", "11012", "11013", "11011"]:
            try:
                df = dart.finstate(corp_code, year, reprt_code=reprt_code)
                if df is None or df.empty:
                    # 전년도도 시도
                    df = dart.finstate(corp_code, year - 1, reprt_code="11011")
                    if df is None or df.empty:
                        continue

                # EPS (기본주당순이익)
                eps_mask = df["account_nm"].str.contains(
                    "기본주당순이익|주당순이익|주당이익", na=False
                )
                eps_rows = df[eps_mask]

                # 매출액
                rev_mask = df["account_nm"].str.contains(
                    "^매출액$|^수익\\(매출액\\)$", na=False, regex=True
                )
                rev_rows = df[rev_mask]

                if eps_rows.empty:
                    continue

                eps_cur  = _parse_amount(eps_rows.iloc[0].get("thstrm_amount"))
                eps_prev = _parse_amount(eps_rows.iloc[0].get("frmtrm_amount"))

                rev_cur  = _parse_amount(rev_rows.iloc[0].get("thstrm_amount")) if not rev_rows.empty else None
                rev_prev = _parse_amount(rev_rows.iloc[0].get("frmtrm_amount")) if not rev_rows.empty else None

                eps_yoy = None
                if eps_cur is not None and eps_prev and eps_prev != 0:
                    eps_yoy = round((eps_cur - eps_prev) / abs(eps_prev), 4)

                rev_yoy = None
                if rev_cur is not None and rev_prev and rev_prev != 0:
                    rev_yoy = round((rev_cur - rev_prev) / abs(rev_prev), 4)

                return {
                    "ticker":       ticker,
                    "eps_current":  eps_cur,
                    "eps_prev_year": eps_prev,
                    "eps_yoy":      eps_yoy,
                    "rev_yoy":      rev_yoy,
                    "canslim_c":    bool(eps_yoy is not None and eps_yoy >= 0.25),
                }
            except Exception:
                continue

        return base
    except Exception:
        return base


def fetch_batch(tickers: list[str]) -> pd.DataFrame:
    if not os.environ.get("DART_API_KEY"):
        print("DART_API_KEY 없음 — 펀더멘털 스킵")
        return pd.DataFrame({"ticker": tickers})

    dart = _client()
    results = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_one, dart, t): t for t in tickers}
        for i, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if i % 20 == 0:
                print(f"DART 수집: {i}/{len(tickers)}")

    df = pd.DataFrame(results)
    for col in ["eps_current", "eps_prev_year", "eps_yoy", "rev_yoy", "canslim_c"]:
        if col not in df.columns:
            df[col] = None
    return df
