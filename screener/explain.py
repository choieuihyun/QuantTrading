"""
종목별 패턴 판정 설명 — "이 종목이 왜 목록에 없지?"에 답한다.

점수 0점은 세 가지를 구분 못 한다: 대상 제외(거래정지·거래대금 미달), 게이트 탈락,
게이트는 통과했는데 점수 미달. 화면에서 이 셋이 같아 보이면 아무것도 알 수 없다.

게이트 판정의 진실은 screener.REQUIRED_FNS 한 곳에 있다. 여기 조건 목록은 설명 전용이라
두 경로가 어긋나면 화면이 거짓말을 하게 된다 — verify()가 패널 전체로 동치를 검사한다.
"""

from screener import (REQUIRED_FNS, SCORE_FNS, SCORE_THRESHOLD, _base_ok,
                      ALL_PATTERN_KEYS, TREND_PATTERN_KEYS, ACCUM_PATTERN_KEYS,
                      CUSTOM_PATTERN_KEYS)


def _num(v):
    """DataFrame.to_dict는 numpy 타입을 주는데 np.int64는 int의 하위형이 아니다.
    isinstance로 거르면 조용히 0이 되어 조건 판정이 뒤집힌다."""
    if v is None or isinstance(v, (bool, str)):
        return 0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return 0 if f != f else f          # NaN


def _fmt(v):
    if v is None:
        return "없음"
    if isinstance(v, (bool,)) or type(v).__name__ == "bool_":
        return "예" if v else "아니오"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f != f:
        return "없음"
    return f"{f:,.0f}" if f == int(f) and abs(f) >= 1000 else f"{f:,.2f}".rstrip("0").rstrip(".")


def ge(label, field, thr):
    """field >= thr. thr가 문자열이면 cfg에서 읽는다."""
    def _t(c):
        return c[thr] if isinstance(thr, str) else thr
    return (label,
            lambda s, c: _num(s.get(field)) >= _t(c),
            lambda s, c: f"{_fmt(s.get(field))} / 기준 {_fmt(_t(c))} 이상")


def gt_field(label, field, other):
    return (label,
            lambda s, c: _num(s.get(field)) > _num(s.get(other)),
            lambda s, c: f"{_fmt(s.get(field))} vs {_fmt(s.get(other))}")


def flag(label, field):
    return (label,
            lambda s, c: bool(s.get(field)),
            lambda s, c: _fmt(bool(s.get(field))))


def any_flag(label, fields, names):
    return (label,
            lambda s, c: any(bool(s.get(f)) for f in fields),
            lambda s, c: " 또는 ".join(f"{n} {_fmt(bool(s.get(f)))}"
                                      for f, n in zip(fields, names)))


def exists(label, field):
    return (label,
            lambda s, c: s.get(field) is not None,
            lambda s, c: _fmt(s.get(field)))


# screener.REQUIRED_FNS와 조건이 1:1로 대응해야 한다 (verify가 검사)
GATE_CONDITIONS = {
    "p1": [
        flag("부분 정배열", "partial_aligned"),
        any_flag("OBV 상승 또는 볼린저 수축", ["obv_rising", "bb_squeeze"], ["OBV↑", "BB수축"]),
    ],
    "p2": [
        flag("완전 정배열", "full_aligned"),
        flag("주가가 5일선 위", "price_above_ma5"),
        ge("MACD 양수", "macd", 1e-12),
    ],
    "p3": [
        flag("눌림목 구간", "is_pullback_range"),
        flag("20일선 위", "above_ma20"),
    ],
    "canslim": [
        ge("N — 52주 위치 (신고가 25% 이내)", "pos_52w", 0.75),
        ge("L — RS Rating (전 종목 백분위)", "rs_rating", 70),
        flag("M — 시장 상승 국면", "market_uptrend"),
        ge("S — 거래량 급증", "vol_ratio", "vol_ratio_buy"),
    ],
    "vcp": [
        flag("Trend Template 통과", "tt_ok"),
        ge("RS Rating", "rs_rating", 70),
        ge("수축 구간 수", "vcp_legs", 2),
        flag("수축이 좁아지는 중", "vcp_tightening"),
    ],
    "stage2": [
        gt_field("주가가 150일선 위", "price", "ma150"),
        flag("150일선 우상향", "ma150_rising"),
        flag("베이스 저항 돌파", "recent_breakout"),
        ge("돌파 거래량", "breakout_vol", 2.0),
    ],
    "wyckoff": [
        exists("거래범위 형성", "range_high"),
        any_flag("Spring 또는 SOS", ["wyckoff_spring", "wyckoff_sos"], ["Spring", "SOS"]),
        flag("하락일 거래량 마름", "wyckoff_vol_dry"),
    ],
    "darvas": [
        flag("박스 확정", "box_ready"),
        flag("박스 천장 돌파", "box_breakout"),
        ge("거래량 급증", "vol_ratio", "vol_ratio_buy"),
    ],
}

COMMON_SPECS = {
    "common_trend": TREND_PATTERN_KEYS,
    "common_accum": ACCUM_PATTERN_KEYS,
    "common_all":   CUSTOM_PATTERN_KEYS,
}

# 원전이 정한 진입 기준점과 손절. (기준점 필드, 손절 필드, 기준일 필드, 라벨)
# 점수는 "구조가 맞는가", 기준점은 "지금이 그 자리인가" — 다른 질문이라 따로 싣는다.
# 여기 기준점을 바꾸면 화면의 ENTRY_STATS(패턴별 근접도 실측)가 다른 것을 재게 된다.
ENTRY_REF = {
    "vcp":     ("vcp_pivot",  "vcp_stop",  "vcp_pivot_date", "마지막 수축 고점"),
    "darvas":  ("box_top",    "stop_box",  None,             "박스 천장"),
    "stage2":  ("range_high", "range_low", None,             "베이스 저항"),
    "wyckoff": ("range_high", "range_low", None,             "거래범위 상단"),
}


def entry_info(key: str, s: dict) -> dict | None:
    """기준점 대비 현재 위치. 게이트 탈락 종목도 실어야 '언제 사야 했나'를 볼 수 있다."""
    ref = ENTRY_REF.get(key)
    if not ref:
        return None
    pivot_f, stop_f, date_f, label = ref
    pivot, price = _num(s.get(pivot_f)), _num(s.get("price"))
    if pivot <= 0 or price <= 0:
        return None
    out = {"lb": label, "pv": pivot, "gap": round(price / pivot - 1, 4)}
    day = s.get(date_f) if date_f else None
    if day:
        out["pd"] = str(day)[5:]
    stop = _num(s.get(stop_f))
    if stop > 0:
        out["st"] = stop
        out["sg"] = round(stop / price - 1, 4)
    return out


def base_exclusion(s: dict, cfg: dict) -> str | None:
    """대상 제외 사유. 통과면 None."""
    if not s.get("is_tradable"):
        return "거래 불가 — 최근 20일 중 거래량 0인 날이 3일 이상이거나 가격이 고정됨"
    mv = cfg.get("min_trading_value")
    if mv and _num(s.get("avg_value_20")) < mv:
        return (f"거래대금 미달 — 20일 평균 {_fmt(round(_num(s.get('avg_value_20'))))} "
                f"< 기준 {_fmt(mv)}")
    return None


def explain(s: dict, cfg: dict, threshold: float = None) -> dict:
    """
    한 종목의 전 패턴 판정.
      state: excluded(대상 제외) | gate_fail(게이트 탈락) | low_score(점수 미달) | pass
    """
    thr = threshold if threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)
    excl = base_exclusion(s, cfg)

    out = {}
    for key in ALL_PATTERN_KEYS:
        if excl:
            out[key] = {"state": "excluded", "score": 0.0, "reason": excl, "conds": []}
            continue
        conds = [{"label": lab, "ok": bool(ok(s, cfg)), "detail": det(s, cfg)}
                 for lab, ok, det in GATE_CONDITIONS[key]]
        if not all(c["ok"] for c in conds):
            fail = next(c for c in conds if not c["ok"])
            out[key] = {"state": "gate_fail", "score": 0.0, "conds": conds,
                        "reason": f"{fail['label']} — {fail['detail']}"}
            continue
        score = round(float(SCORE_FNS[key](s, cfg)), 1)
        out[key] = {
            "state": "pass" if score >= thr else "low_score",
            "score": score, "conds": conds,
            "reason": None if score >= thr else f"점수 {score} < 기준 {thr}",
        }

    for name, keys in COMMON_SPECS.items():
        hits = [k for k in keys if out[k]["state"] == "pass"]
        need = min(2, len(keys))
        out[name] = {
            "state": "pass" if len(hits) >= need else "gate_fail",
            "score": round(sum(out[k]["score"] for k in keys) / len(keys), 1),
            "hits": hits, "need": need, "members": list(keys), "conds": [],
            "reason": None if len(hits) >= need
                      else f"{len(hits)}/{need}개 통과 ({', '.join(hits) if hits else '없음'})",
        }
    return out


def verify(market: str = "kr") -> int:
    """
    설명용 조건 목록이 실제 게이트와 같은 판정을 내는지 패널 전체로 검사.

    여기가 어긋나면 화면이 "이 조건 때문에 탈락"이라고 하는데 실제 판정은 다른 이유가 된다.
    화면 설명과 코드가 따로 노는 건 이 프로젝트에서 이미 한 번 잡힌 버그다.
    """
    import pandas as pd
    from replay import CACHE_DIR
    from market_config import ALL_CONFIGS

    path = CACHE_DIR / f"panel_{market}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — python replay.py build --market {market}")

    cfg = ALL_CONFIGS[market]
    rows = pd.read_parquet(path).to_dict("records")
    bad = 0
    for i, s in enumerate(rows):
        if base_exclusion(s, cfg):
            continue
        for key in ALL_PATTERN_KEYS:
            mine = all(bool(ok(s, cfg)) for _, ok, _ in GATE_CONDITIONS[key])
            real = bool(REQUIRED_FNS[key](s, cfg))
            if mine != real:
                bad += 1
                if bad <= 5:
                    print(f"불일치 [{key}] {s.get('ticker')} {s.get('date')}: "
                          f"설명={mine} 실제={real}")
    print(f"\n검사 {len(rows):,}행 × {len(ALL_PATTERN_KEYS)}패턴 — "
          f"{'불일치 ' + str(bad) + '건' if bad else '전부 일치 ✓'}")

    # 게이트 판정이 맞아도 업로드가 터지면 화면에는 옛날 데이터가 남는다.
    # entry_info 미정의로 pack()이 통째로 죽은 채 커밋된 적이 있다 — main.py가 예외를 삼킨다.
    bad += _verify_pack(rows[-3000:], cfg)
    return bad


def _verify_pack(rows: list, cfg: dict) -> int:
    """게이트 통과 건에는 기준점과 손절이 반드시 실려야 한다.
    'e'만 세면 손절 필드가 None이 돼도 통과한다 — 화면에서 손절 줄만 조용히 사라진다."""
    seen = {k: [0, 0, 0] for k in ENTRY_REF}        # 통과, 기준점, 손절
    for s in rows:
        for k, v in (pack(s, cfg).get("p") or {}).items():   # 예외는 그대로 터뜨린다
            if k in seen and v["s"] == "p":
                seen[k][0] += 1
                seen[k][1] += "e" in v
                seen[k][2] += "st" in v.get("e", {})

    # 패널은 라이브보다 오래된 스키마다. 컬럼이 아예 없는 것과 값이 비는 것은 다른 문제다.
    cols = set(rows[0]) if rows else set()
    print(f"pack() {len(rows):,}행 통과 — 게이트 통과 건의 기준점/손절 적재")
    bad = 0
    for k, (n, e, st) in seen.items():
        stale = ENTRY_REF[k][1] not in cols
        ok = n and e == n and (st == n or stale)
        print(f"  {'✓' if ok else '—' if not n else '✗'} {k:8} 통과 {n:5,} · "
              f"기준점 {e:5,} · 손절 {'패널 미보유' if stale else f'{st:5,}'}")
        bad += bool(n) and not ok
    return bad



# ── 업로드용 압축 ────────────────────────────────────────
# 조건 라벨은 종목마다 같으므로 인덱스 문서에 한 번만 두고, 종목별로는 통과여부+실측값만 담는다.
# 전 종목 × 11패턴 × 조건 상세는 한 문서(1MB)에 안 들어가 샤드로 쪼갠다.
SHARDS = 8
STATE_CODE = {"excluded": "x", "gate_fail": "g", "low_score": "l", "pass": "p"}


def shard_of(ticker: str) -> int:
    """대시보드(TypeScript)와 반드시 같은 식이어야 한다.
    한국 종목코드는 끝자리가 전부 0이라 마지막 글자로 나누면 한 샤드에 다 몰린다."""
    return sum(ord(c) for c in str(ticker)) % SHARDS


def labels() -> dict:
    return {k: [lab for lab, _, _ in conds] for k, conds in GATE_CONDITIONS.items()}


def pack(s: dict, cfg: dict, threshold: float = None) -> dict:
    excl = base_exclusion(s, cfg)
    if excl:
        return {"x": excl}
    ex = explain(s, cfg, threshold)
    # Firestore는 배열 요소로 배열을 허용하지 않는다. 조건을 [[통과, 값], ...]로 담으면
    # 문서 전체가 거부되고 화면에는 "데이터 없음"만 남는다. 맵의 배열로 담는다.
    p = {}
    for k in ALL_PATTERN_KEYS:
        v = ex[k]
        p[k] = {"s": STATE_CODE[v["state"]], "v": v["score"],
                "c": [{"o": bool(c["ok"]), "d": c["detail"]} for c in v["conds"]]}
        ent = entry_info(k, s)
        if ent:
            p[k]["e"] = ent
    for k in COMMON_SPECS:
        p[k] = {"s": STATE_CODE[ex[k]["state"]], "v": ex[k]["score"], "h": list(ex[k]["hits"])}
    return {"p": p}


def build_shards(rows: list, cfg: dict, threshold: float = None) -> dict:
    """반환: {샤드번호: {ticker: packed}}"""
    out = {i: {} for i in range(SHARDS)}
    for s in rows:
        t = str(s.get("ticker"))
        if t:
            out[shard_of(t)][t] = pack(s, cfg, threshold)
    return out


if __name__ == "__main__":
    import sys
    raise SystemExit(1 if verify(sys.argv[1] if len(sys.argv) > 1 else "kr") else 0)
