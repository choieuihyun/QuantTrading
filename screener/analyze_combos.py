"""패턴 조합 실측 — "2개 이상 겹치면 신뢰도가 올라간다"가 사실인지 확인.

common_trend는 '4개 중 2개'로 정해져 있지만 어느 쌍이 실제로 나은지 측정한 적이 없다.

주의해서 봐야 할 두 가지:
  1) 종목중앙차 — 유니버스 중앙 종목 대비. 몇 명이서 3~5종목 골라 사는 실제 경험에
     가까운 값이다. 평균은 우측 꼬리 하나에 끌려간다.
  2) t — 20일 보유를 5일 간격으로 스캔하므로 날짜가 4중으로 겹친다.
     Newey-West(4랙)로 보정한다. 겹침을 무시하면 |t|가 2배로 부풀어 오른다.

  python analyze_combos.py [--hold 20] [--market kr]
"""

import argparse
import itertools

import numpy as np
import pandas as pd

from replay import CACHE_DIR
from screener import (score_pattern, ALL_PATTERN_KEYS, SCORE_THRESHOLD,
                      TREND_PATTERN_KEYS, CUSTOM_PATTERN_KEYS)
from market_config import ALL_CONFIGS

MIN_PICKS = 60    # 이보다 적으면 표본이 얇아 비교 의미 없음
MIN_DATES = 15
TOP_N = 20        # 화면에 실제로 노출되는 개수


def nw_t(x: pd.Series, lags: int) -> float:
    """Newey-West 보정 t. 겹치는 보유기간 때문에 날짜별 초과수익은 자기상관이 있다."""
    n = len(x)
    if n <= lags + 1:
        return float("nan")
    d = x.values - x.values.mean()
    var = (d @ d) / n
    for l in range(1, lags + 1):
        cov = (d[l:] @ d[:-l]) / n
        var += 2 * (1 - l / (lags + 1)) * cov
    return float("nan") if var <= 0 else x.mean() / np.sqrt(var / n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    ap.add_argument("--hold", type=int, default=20, choices=[5, 20, 60])
    ap.add_argument("--threshold", type=float, default=None)
    a = ap.parse_args()

    cfg = ALL_CONFIGS[a.market]
    thr = a.threshold if a.threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)
    col = f"ret_{a.hold}"

    path = CACHE_DIR / f"panel_{a.market}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — python replay.py build --market {a.market}")
    p = pd.read_parquet(path)
    rows = p.to_dict("records")
    for k in ALL_PATTERN_KEYS:
        p[f"s_{k}"] = [score_pattern(k, r, cfg) for r in rows]
        p[f"f_{k}"] = p[f"s_{k}"] >= thr

    # 화면의 common_* 게이트를 그대로 재현
    for name, keys in [("common_trend", TREND_PATTERN_KEYS),
                       ("common_all", CUSTOM_PATTERN_KEYS)]:
        need = min(2, len(keys))
        p[f"f_{name}"] = sum(p[f"f_{k}"].astype(int) for k in keys) >= need
        p[f"s_{name}"] = sum(p[f"s_{k}"] for k in keys) / len(keys)

    uni = p[p["is_tradable"]].dropna(subset=[col])
    base = uni.groupby("date")[col].mean()
    um = uni.merge(base.rename("b"), on="date")
    uni_med = (um[col] - um["b"]).median()
    # 스캔 간격 대비 보유기간이 몇 겹인지 = 자기상관 랙
    gap = max(1, int(round(np.median(
        np.diff(pd.to_datetime(pd.Series(sorted(base.index)))).astype("timedelta64[D]").astype(float)))))
    lags = max(1, min(len(base) // 4, round(a.hold * 7 / 5 / gap)))

    print(f"\n패널 {len(p):,}행 / {len(base)}일 "
          f"({str(p['date'].min())[:10]} ~ {str(p['date'].max())[:10]})")
    print(f"보유 {a.hold}일 · 임계 {thr}점 · 시장 상승 구간 {p['market_uptrend'].mean()*100:.0f}%")
    print(f"유니버스 종목 중앙 초과 {uni_med*100:+.2f}% 기준 · Newey-West {lags}랙 "
          f"(스캔 간격 {gap}일) · |t|>2 라야 노이즈와 구별\n")

    def stats(sel, label, indent=""):
        sel = sel.dropna(subset=[col])
        if sel.empty:
            return None
        per = sel.groupby("date")[col].mean()
        ex = (per - base.reindex(per.index)).dropna()
        if len(ex) < MIN_DATES:
            return None
        m = sel.merge(base.rename("b"), on="date")
        med_gap = (m[col] - m["b"]).median() - uni_med
        drop1 = ex.drop(ex.idxmax()).mean()
        print(f"{indent + label:24} {ex.mean()*100:+8.2f}% {ex.median()*100:+8.2f}% "
              f"{drop1*100:+9.2f}% {med_gap*100:+9.2f}%p {nw_t(ex, lags):7.2f} "
              f"{len(sel):7,} {len(ex):4d}")
        return ex.mean()

    hdr = (f"{'':24} {'날짜평균':>9} {'날짜중앙':>9} {'최고날제외':>10} "
           f"{'종목중앙차':>10} {'t':>7} {'건수':>7} {'날짜':>4}")

    # ── 화면에 실제로 뜨는 목록 ──
    print("■ 화면 노출 목록 (게이트 통과 전체 / 점수 상위 20)")
    print(hdr)
    print("-" * 92)
    for name in ["common_trend", "common_all"]:
        stats(p[p[f"f_{name}"]], name)
        top = (p[p[f"f_{name}"]].sort_values(f"s_{name}", ascending=False)
               .groupby("date").head(TOP_N))
        stats(top, f"└ 상위{TOP_N}", indent="")

    # ── 단독 ──
    print(f"\n■ 단독 패턴\n{hdr}")
    print("-" * 92)
    solo = {}
    for k in ALL_PATTERN_KEYS:
        v = stats(p[p[f"f_{k}"]], k)
        if v is not None:
            solo[k] = v

    # ── 2개 조합 ──
    combos = []
    for x, y in itertools.combinations(ALL_PATTERN_KEYS, 2):
        both = p[p[f"f_{x}"] & p[f"f_{y}"]]
        if len(both) < MIN_PICKS:
            print(f"\n[표본 부족] {x} + {y}: {len(both)}건 — 측정 제외")
            continue
        b = both.dropna(subset=[col])
        per = b.groupby("date")[col].mean()
        ex = (per - base.reindex(per.index)).dropna()
        if len(ex) < MIN_DATES:
            continue
        # 두 단독의 평균보다 나아졌는지 = 겹침이 실제로 정보를 더하는지
        combos.append((ex.mean() - (solo.get(x, 0) + solo.get(y, 0)) / 2, x, y, both))

    combos.sort(reverse=True)
    print(f"\n■ 2개 조합 — 단독 평균 대비 개선폭 순\n{hdr}")
    print("-" * 92)
    for lift, x, y, both in combos:
        stats(both, f"{x}+{y} ({lift*100:+.1f}%p)")

    if combos:
        gains = sum(1 for c in combos if c[0] > 0)
        print(f"\n조합 {len(combos)}개 중 단독 평균보다 나은 것 {gains}개 "
              f"({gains/len(combos)*100:.0f}%)")
        print("→ 절반 근처면 '겹치면 낫다'는 가정에 근거가 없다는 뜻이다.")
        print("→ 날짜평균만 보지 마라. 중앙값이 음수인데 평균이 양수면 하루짜리 꼬리다.")


if __name__ == "__main__":
    main()
