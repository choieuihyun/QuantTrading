"""
돌파 대기 — 아직 발동하지 않은 패턴의 '발동가'를 미리 알려준다.

스크리너는 하루 3번만 돈다. 돌파는 장중에 일어나므로 목록에 뜰 때는 이미 며칠 지난 뒤다.
그래서 "얼마가 되면 이 패턴이 뜨는가"를 먼저 알아야 증권사 알림을 걸어둘 수 있다.

**매수 신호가 아니다.** 발동가는 사실 진술이다 — "이 가격을 넘으면 조건이 충족된다".
돌파 지점에서 사는 것이 이득이라는 실측 근거는 없다 (Darvas 돌파 후 선정력이
표본에 따라 −1.23% ↔ +0.53%로 부호가 뒤집힌다).
"""

import pandas as pd

MAX_GAP = 0.15        # 발동가가 이보다 멀면 '대기'라고 부를 수 없다
MAX_ROWS = 60         # 화면에 담기는 양. 넘으면 가까운 순으로 자른다


def _n(v) -> float:
    """numpy 타입과 NaN을 한 번에 거른다 — np.int64는 int의 하위형이 아니다."""
    if v is None or isinstance(v, (bool, str)):
        return 0.0
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f != f else f


# (발동가, 손절, 라벨, 발동가를 넘으면 무슨 일이 일어나는가, 나머지 게이트)
#
# VCP만 성격이 다르다. VCP 게이트에는 돌파 조건이 없어서 게이트가 먼저 통과되고
# 피벗은 Minervini가 말하는 '진입가'다. 그래서 4게이트를 다 통과한 뒤에도
# 피벗 아래인 종목만 대기로 잡는다 (실측: 통과 건의 19%, 날짜당 3.6종목).
SPECS = {
    "vcp": ("vcp_pivot", "vcp_stop", "VCP 피벗",
            "원전(Minervini) 진입가 — 게이트는 이미 통과했습니다",
            lambda r: (bool(r.get("tt_ok")) and _n(r.get("rs_rating")) >= 70
                       and _n(r.get("vcp_legs")) >= 2 and bool(r.get("vcp_tightening")))),
    "darvas": ("box_top", "stop_box", "Darvas 박스천장",
               "넘으면 box_breakout이 켜지고 Darvas가 발동합니다",
               lambda r: bool(r.get("box_ready"))),
    "stage2": ("range_high", "range_low", "Stage 2 베이스저항",
               "넘으면 recent_breakout이 켜집니다 (거래량 2배도 함께 필요)",
               lambda r: (_n(r.get("price")) > _n(r.get("ma150")) > 0
                          and bool(r.get("ma150_rising"))
                          and r.get("range_high") is not None)),
}


def build(rows: list, cfg: dict) -> list:
    """반환: 발동가까지 가까운 순으로 정렬된 대기 행. 한 종목이 여러 패턴에 걸릴 수 있다."""
    mv = cfg.get("min_trading_value") or 0
    out = []
    for r in rows:
        if _n(r.get("avg_value_20")) < mv or not r.get("is_tradable"):
            continue
        price = _n(r.get("price"))
        if price <= 0:
            continue
        for key, (trig_f, stop_f, label, effect, gate) in SPECS.items():
            try:
                if not gate(r):
                    continue
            except (TypeError, KeyError):
                continue
            trig = _n(r.get(trig_f))
            # 이미 넘었으면 대기가 아니다 — 그 종목은 패턴 목록 쪽에 뜬다
            if trig <= 0 or price >= trig:
                continue
            gap = trig / price - 1
            if gap > MAX_GAP:
                continue
            stop = _n(r.get(stop_f))
            out.append({
                "t": str(r.get("ticker")),
                "n": str(r.get("name") or r.get("ticker")),
                "k": key,                                   # 패턴 키 — 화면에서 라벨·색으로 쓴다
                "lb": label,
                "ef": effect,
                "pr": round(price, 2),
                "tg": round(trig, 2),
                "g": round(gap, 4),
                "st": round(stop, 2) if stop > 0 else None,
                # 발동가에 사서 원전 손절을 지키면 감수해야 하는 폭. 패턴마다 크게 다르다.
                "sl": round(stop / trig - 1, 4) if stop > 0 else None,
                "rs": round(_n(r.get("rs_rating")), 0) or None,
            })
    out.sort(key=lambda x: x["g"])
    return out[:MAX_ROWS]


def summarize(rows: list) -> str:
    if not rows:
        return "돌파 대기 0종목 — 발동가 근처에 온 종목이 없습니다"
    per = pd.Series([r["k"] for r in rows]).value_counts().to_dict()
    near = sum(1 for r in rows if r["g"] <= 0.03)
    return (f"돌파 대기 {len(rows)}종목 ("
            + " · ".join(f"{k} {v}" for k, v in per.items())
            + f") · 3% 이내 {near}종목")
