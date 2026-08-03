"""
DART 재무 수집 + 파생지표 계산.

핵심(프로브로 검증됨):
- 분기보고서(11013/11012/11014)의 손익 thstrm_amount = 당기 3개월 단독값.
  → 누적 차감 불필요. 사업보고서(11011) thstrm_amount만 연간(=Q4는 연간−3Q누적).
- 재무상태표(재고/자산/부채/자본)는 시점값 → 그대로 사용.
- 회사마다 계정명이 다르므로 account_id(IFRS 코드)로 매칭. sj_div로 재무제표 종류 선구분.
"""
import os
import pandas as pd
import OpenDartReader as ODR
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# reprt_code → 분기번호 (11013=1Q, 11012=반기=2Q, 11014=3Q, 11011=사업보고서=Q4/연간)
REPRT_Q = {"11013": 1, "11012": 2, "11014": 3, "11011": 4}
REPRT_ORDER = ["11011", "11014", "11012", "11013"]  # 한 해 안에서 최신 분기부터

# 손익계산서를 IS로 내는 회사(삼성)와 CIS(포괄손익)로만 내는 회사(하이닉스)가 섞여 있음 → 둘 다 탐색
IS_DIVS = ("IS", "CIS")

# (statement_group, [account_id 후보]) — group "IS"=손익(IS/CIS), "BS"=재무상태표. 프로브로 확인.
ACCOUNTS = {
    "rev":        ("IS", ["ifrs-full_Revenue", "ifrs-full_RevenueFromContractsWithCustomers"]),
    "cogs":       ("IS", ["ifrs-full_CostOfSales"]),
    "op":         ("IS", ["dart_OperatingIncomeLoss"]),
    "net":        ("IS", ["ifrs-full_ProfitLoss"]),
    "eps":        ("IS", ["ifrs-full_BasicEarningsLossPerShare"]),
    "assets":     ("BS", ["ifrs-full_Assets"]),
    "liab":       ("BS", ["ifrs-full_Liabilities"]),
    "equity":     ("BS", ["ifrs-full_Equity"]),
    "inventory":  ("BS", ["ifrs-full_Inventories"]),
    "receivables":("BS", ["ifrs-full_CurrentTradeReceivables", "ifrs-full_TradeAndOtherCurrentReceivables"]),
    "cash":       ("BS", ["ifrs-full_CashAndCashEquivalents"]),
}
FLOW_FIELDS = {"rev", "cogs", "op", "net", "eps"}  # 손익 = 흐름값


def _client():
    return ODR(os.environ["DART_API_KEY"])


def _num(val) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "").replace(" ", "").replace("△", "-")
    if not s or s in ("nan", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fetch_period(dart, corp_code: str, year: int, reprt: str) -> dict | None:
    """한 분기 재무 → 원본값 dict. 연결(CFS) 우선, 없으면 별도(OFS)."""
    df = None
    for fs_div in ("CFS", "OFS"):
        try:
            df = dart.finstate_all(corp_code, year, reprt_code=reprt, fs_div=fs_div)
        except Exception:
            df = None
        if df is not None and not df.empty:
            break
    if df is None or df.empty or "account_id" not in df.columns:
        return None

    rec = {"y": year, "q": REPRT_Q[reprt], "reprt": reprt}
    for field, (grp, acc_ids) in ACCOUNTS.items():
        divs = ("BS",) if grp == "BS" else IS_DIVS
        rows = df[(df["sj_div"].isin(divs)) & (df["account_id"].isin(acc_ids))]
        rec[field] = _num(rows.iloc[0].get("thstrm_amount")) if not rows.empty else None
        # 손익 누적값(9개월 등) — 연간의 Q4 단독 계산에 필요
        if field in FLOW_FIELDS:
            rec[field + "_cum"] = (
                _num(rows.iloc[0].get("thstrm_add_amount")) if not rows.empty else None
            )
    return rec


# 분기별 공시 마감(대략): Q1 5/15, 반기 8/15, Q3 11/15, 사업보고서 익년 4/1.
# 마감 전 분기는 조회해도 미공시라 dead call → 스킵.
_DUE = {1: (5, 15), 2: (8, 15), 3: (11, 15), 4: None}  # 4는 익년 4/1 특수처리


def _is_due(year: int, q: int, today) -> bool:
    if q == 4:
        return (today.year, today.month, today.day) >= (year + 1, 4, 1)
    m, d = _DUE[q]
    return (today.year, today.month, today.day) >= (year, m, d)


def fetch_history(dart, corp_code: str, existing: dict | None = None, want: int = 8) -> dict:
    """
    최근 want개 분기 원본 재무 히스토리. existing에 이미 있는 분기는 건너뜀(증분).
    반환: { "2024Q3": {rec}, ... }
    """
    hist = dict(existing or {})
    today = datetime.today()
    year = today.year
    got = len(hist)
    attempts = 0
    while got < want and attempts < want + 6:
        for reprt in REPRT_ORDER:
            q = REPRT_Q[reprt]
            key = f"{year}Q{q}"
            if key in hist or not _is_due(year, q, today):
                continue
            rec = _fetch_period(dart, corp_code, year, reprt)
            attempts += 1
            if rec is None:
                continue  # 아직 미공시거나 데이터 없음
            hist[key] = rec
            got += 1
            if got >= want:
                break
        year -= 1
        if year < datetime.today().year - 4:  # 4년 이상은 안 봄
            break
    return hist


def _single_flow(hist_list: list, field: str) -> dict:
    """(y,q) → 단일 분기 흐름값. Q1~3는 thstrm 그대로, Q4(연간)는 연간−3Q누적."""
    out = {}
    for r in hist_list:
        y, q = r["y"], r["q"]
        val = r.get(field)
        if q in (1, 2, 3):
            out[(y, q)] = val
        else:  # 연간 → Q4 단독 = 연간 − 같은해 3Q 누적
            q3 = next((x for x in hist_list if x["y"] == y and x["q"] == 3), None)
            q3cum = q3.get(field + "_cum") if q3 else None
            out[(y, q)] = (val - q3cum) if (val is not None and q3cum is not None) else None
    return out


def _ttm(single: dict, keys_desc: list) -> float | None:
    """최신 4개 분기 단독값 합. 중간 분기가 누락돼 4개가 연속이 아니면 None(조용한 오류 방지).
    rate-limit(020)와 미공시가 구분 안 되므로, 비연속이면 합산하지 않는다."""
    ks = keys_desc[:4]
    if len(ks) < 4:
        return None
    for a, b in zip(ks, ks[1:]):  # a가 b보다 한 분기 뒤(최신순) — b는 a의 직전 분기여야
        prev = (a[0], a[1] - 1) if a[1] > 1 else (a[0] - 1, 4)
        if b != prev:
            return None
    vals = [single.get(k) for k in ks]
    return None if any(v is None for v in vals) else sum(vals)


def _ratio(a, b):
    if a is None or b is None or b == 0:
        return None
    return round(a / b, 4)


def derive(hist: dict) -> dict:
    """원본 히스토리 → 파생 스칼라(TTM/성장성/수익성/안정성/재고)."""
    out = {
        "eps_current": None, "eps_prev_year": None, "eps_yoy": None, "rev_yoy": None,
        "canslim_c": False, "ttm_revenue": None, "ttm_op_income": None,
        "ttm_net_income": None, "latest_equity": None, "latest_assets": None,
        "latest_liabilities": None, "latest_inventory": None, "roe": None, "roa": None,
        "op_margin": None, "net_margin": None, "debt_ratio": None,
        "inventory_qoq": None, "inventory_yoy": None, "inventory_turnover": None,
        "latest_period": None,
    }
    if not hist:
        return out

    hlist = sorted(hist.values(), key=lambda r: (r["y"], r["q"]))
    keys_desc = sorted(hist.keys(), key=lambda k: (hist[k]["y"], hist[k]["q"]), reverse=True)
    latest = hist[keys_desc[0]]
    out["latest_period"] = keys_desc[0]

    # 시점값(BS)
    out["latest_equity"] = latest.get("equity")
    out["latest_assets"] = latest.get("assets")
    out["latest_liabilities"] = latest.get("liab")
    out["latest_inventory"] = latest.get("inventory")

    # TTM(흐름)
    kd = [(hist[k]["y"], hist[k]["q"]) for k in keys_desc]
    rev_s = _single_flow(hlist, "rev")
    op_s  = _single_flow(hlist, "op")
    net_s = _single_flow(hlist, "net")
    eps_s = _single_flow(hlist, "eps")
    cogs_s = _single_flow(hlist, "cogs")
    out["ttm_revenue"]    = _ttm(rev_s, kd)
    out["ttm_op_income"]  = _ttm(op_s, kd)
    out["ttm_net_income"] = _ttm(net_s, kd)
    ttm_cogs = _ttm(cogs_s, kd)

    # EPS 성장(전년 동기) — CAN SLIM 'C'
    eps_cur = eps_s.get(kd[0])
    eps_prev = eps_s.get((kd[0][0] - 1, kd[0][1])) if kd else None
    out["eps_current"] = eps_cur
    out["eps_prev_year"] = eps_prev
    if eps_cur is not None and eps_prev not in (None, 0):
        out["eps_yoy"] = round((eps_cur - eps_prev) / abs(eps_prev), 4)
        out["canslim_c"] = bool(out["eps_yoy"] >= 0.25)

    # 매출 성장(전년 동기 단독)
    rev_cur = rev_s.get(kd[0])
    rev_prev = rev_s.get((kd[0][0] - 1, kd[0][1])) if kd else None
    if rev_cur is not None and rev_prev not in (None, 0):
        out["rev_yoy"] = round((rev_cur - rev_prev) / abs(rev_prev), 4)

    # 수익성/안정성
    out["roe"] = _ratio(out["ttm_net_income"], out["latest_equity"])
    out["roa"] = _ratio(out["ttm_net_income"], out["latest_assets"])
    out["op_margin"] = _ratio(out["ttm_op_income"], out["ttm_revenue"])
    out["net_margin"] = _ratio(out["ttm_net_income"], out["ttm_revenue"])
    out["debt_ratio"] = _ratio(out["latest_liabilities"], out["latest_equity"])

    # 재고 사이클
    inv_now = latest.get("inventory")
    if len(keys_desc) >= 2:
        inv_prev = hist[keys_desc[1]].get("inventory")
        out["inventory_qoq"] = _ratio(
            (inv_now - inv_prev) if (inv_now is not None and inv_prev is not None) else None,
            inv_prev,
        )
    inv_yoy_key = f"{latest['y'] - 1}Q{latest['q']}"
    if inv_yoy_key in hist and inv_now is not None:
        inv_yago = hist[inv_yoy_key].get("inventory")
        out["inventory_yoy"] = _ratio(
            (inv_now - inv_yago) if inv_yago is not None else None, inv_yago
        )
    # 재고회전율 = TTM매출원가 / 최근 재고
    out["inventory_turnover"] = _ratio(ttm_cogs, inv_now)

    return out


def fetch_batch(tickers: list[str], existing_map: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """
    반환: (파생지표 df[ticker 기준], {ticker: {corp_code, quarters}})
    existing_map: {ticker: {quarters}} — 이미 저장된 히스토리(증분 수집용)
    """
    if not os.environ.get("DART_API_KEY"):
        print("DART_API_KEY 없음 — 펀더멘털 스킵")
        return pd.DataFrame({"ticker": tickers}), {}

    dart = _client()
    existing_map = existing_map or {}
    rows, histories = [], {}

    def _one(ticker: str) -> tuple[dict, str | None, dict]:
        try:
            corp = dart.company(ticker)
            if not corp or "corp_code" not in corp:
                return {"ticker": ticker}, None, {}
            corp_code = corp["corp_code"]
            hist = fetch_history(dart, corp_code, existing_map.get(ticker, {}).get("quarters"))
            d = derive(hist)
            d["ticker"] = ticker
            # KSIC 업종코드 — FDR의 Dept가 전부 비어 있어 동종업계 비교는 이걸로 묶음
            d["induty"] = str(corp.get("induty_code") or "")
            return d, corp_code, hist
        except Exception:
            return {"ticker": ticker}, None, {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(_one, t): t for t in tickers}
        for i, fut in enumerate(as_completed(futures), 1):
            d, corp_code, hist = fut.result()
            rows.append(d)
            if corp_code and hist:
                histories[d["ticker"]] = {"corp_code": corp_code, "quarters": hist}
            if i % 20 == 0:
                print(f"DART 수집: {i}/{len(tickers)}")

    df = pd.DataFrame(rows)
    return df, histories


# 종목 row에 남길 표시용 파생지표(대시보드 노출). 원본 큰 숫자(ttm_*/latest_*)는 계산 후 버림.
DISPLAY_COLS = [
    "per", "pbr", "psr", "roe", "roa", "op_margin", "net_margin", "debt_ratio",
    "inventory_qoq", "inventory_yoy", "inventory_turnover",
    "eps_current", "eps_yoy", "rev_yoy", "canslim_c", "latest_period", "induty",
]
_RAW_DROP = [
    "ttm_revenue", "ttm_op_income", "ttm_net_income",
    "latest_equity", "latest_assets", "latest_liabilities", "latest_inventory",
    "eps_prev_year",
]


def add_valuation(df: pd.DataFrame) -> pd.DataFrame:
    """marcap + TTM 재무 → PER/PBR/PSR. 계산 후 원본 큰 숫자 컬럼은 제거(문서 용량↓)."""
    def _v(row, denom_col):
        mc, d = row.get("marcap"), row.get(denom_col)
        if mc in (None, 0) or d in (None, 0) or (isinstance(d, float) and pd.isna(d)):
            return None
        if d <= 0:  # 적자면 PER 의미 없음
            return None
        return round(mc / d, 2)

    df = df.copy()
    df["per"] = df.apply(lambda r: _v(r, "ttm_net_income"), axis=1)
    df["pbr"] = df.apply(lambda r: _v(r, "latest_equity"), axis=1)
    df["psr"] = df.apply(lambda r: _v(r, "ttm_revenue"), axis=1)
    df = df.drop(columns=[c for c in _RAW_DROP if c in df.columns])
    return df
