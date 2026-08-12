"""
차트 구조 탐지 — 박스, 연속 수축, 거래범위.

지표(RSI·MACD 등)와 달리 여기 있는 것들은 '가격 구조'를 찾는다.
원전 규칙을 최대한 그대로 옮기되, 수치가 명시되지 않은 부분은 상수로 빼고 문서에 적었다.

출처
  Darvas   : 신고가가 3봉 이상 경신되지 않으면 천장 확정, 이후 저점이 3봉 버티면 바닥 확정
  Minervini: 조정이 연속으로 얕아지는 구간(2~5회), 거래량도 같이 감소, 마지막 수축 고점이 피벗
  Weinstein: Stage 1 횡보 구간의 저항을 거래량 2배 이상으로 돌파
  Wyckoff  : 거래범위 안에서 Spring(지지 이탈 후 회복) → SOS(거래량 동반 상단 돌파)
"""

import numpy as np
import pandas as pd

SWING_K        = 5     # 좌우 5봉보다 높으면 스윙 고점 (원전에 수치 없음 — 임의 선택)
BOX_CONFIRM    = 3     # Darvas 원전: 3일간 경신되지 않으면 확정
BOX_WINDOW     = 60    # 박스를 찾을 최대 구간
BOX_MAX_WIDTH  = 0.25  # 박스 폭 상한 — 넘으면 횡보가 아니라 추세 (원전에 수치 없음)
BASE_MIN_BARS  = 20    # 베이스로 인정할 최소 횡보 길이 (Weinstein: 길수록 좋음)
BASE_WINDOW    = 120   # 베이스 탐색 최대 길이
BASE_MAX_WIDTH = 0.30  # 횡보로 볼 최대 폭 (원전에 수치 없음)
BASE_EXCLUDE   = 5     # 돌파 직전 봉은 베이스에서 제외 (돌파 자체가 고점이 되지 않도록)
VCP_WINDOW     = 90    # 연속 수축을 찾을 구간
VCP_MIN_LEGS   = 2     # 최소 수축 횟수 (교과서 2~5회)


def swing_points(high: np.ndarray, low: np.ndarray, k: int = SWING_K) -> tuple[list[int], list[int]]:
    """좌우 k봉보다 높은(낮은) 지점 = 스윙 고점(저점)"""
    n = len(high)
    highs, lows = [], []
    for i in range(k, n - k):
        seg_h = high[i - k: i + k + 1]
        seg_l = low[i - k: i + k + 1]
        if high[i] == seg_h.max() and (seg_h.argmax() == k):
            highs.append(i)
        if low[i] == seg_l.min() and (seg_l.argmin() == k):
            lows.append(i)
    return highs, lows


def contractions(high: np.ndarray, low: np.ndarray, volume: np.ndarray,
                 window: int = VCP_WINDOW) -> list[dict]:
    """
    스윙 고점 → 다음 스윙 저점을 한 번의 수축으로 보고 순서대로 나열.
    Minervini VCP는 이 수축들이 점점 얕아지는 것이 정체성이다.
    """
    if len(high) < window:
        return []
    off = len(high) - window
    h, l, v = high[off:], low[off:], volume[off:]

    sh, sl = swing_points(h, l)
    if not sh or not sl:
        return []

    legs = []
    for hi in sh:
        after = [x for x in sl if x > hi]
        if not after:
            continue
        lo = after[0]
        peak, trough = float(h[hi]), float(l[lo])
        if peak <= 0:
            continue
        legs.append({
            "high_i": hi + off,
            "low_i":  lo + off,
            "depth":  (trough - peak) / peak,          # 음수
            "volume": float(v[hi:lo + 1].mean()) if lo > hi else float(v[hi]),
        })

    # 같은 저점을 공유하는 수축은 가장 깊은 것만 남긴다 (겹치는 스윙 제거)
    dedup = {}
    for leg in legs:
        key = leg["low_i"]
        if key not in dedup or leg["depth"] < dedup[key]["depth"]:
            dedup[key] = leg
    return sorted(dedup.values(), key=lambda x: x["low_i"])


def vcp_state(high, low, close, volume) -> dict:
    """
    연속 수축이 성립하는지와 피벗(마지막 수축의 고점) 위치.
    """
    legs = contractions(high, low, volume)
    out = {
        "vcp_legs": len(legs),
        "vcp_tightening": False,
        "vcp_vol_declining": False,
        "vcp_last_depth": None,
        "vcp_pivot": None,
        "vcp_above_pivot": False,
    }
    if len(legs) < VCP_MIN_LEGS:
        return out

    # 마지막 VCP_MIN_LEGS+2개까지만 본다 — 너무 오래된 수축은 현재 베이스와 무관
    legs = legs[-5:]
    depths = [abs(x["depth"]) for x in legs]
    vols   = [x["volume"] for x in legs]

    out["vcp_legs"] = len(legs)
    out["vcp_tightening"] = all(depths[i] < depths[i - 1] for i in range(1, len(depths)))
    out["vcp_vol_declining"] = all(vols[i] < vols[i - 1] for i in range(1, len(vols)))
    out["vcp_last_depth"] = round(depths[-1], 4)

    pivot = float(high[legs[-1]["high_i"]])
    out["vcp_pivot"] = pivot
    out["vcp_above_pivot"] = bool(float(close[-1]) > pivot)
    return out


def darvas_box(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               confirm: int = BOX_CONFIRM, window: int = BOX_WINDOW,
               max_width: float = BOX_MAX_WIDTH) -> dict:
    """
    Darvas 원전 규칙:
      1) 신고가가 confirm봉 동안 경신되지 않으면 그 고가가 박스 천장
      2) 천장 확정 이후 나온 최저가가 confirm봉 동안 깨지지 않으면 박스 바닥
      3) 종가가 천장을 넘으면 매수 신호, 손절은 박스 바닥

    Darvas의 박스는 '좁은 횡보'다. 단순히 구간 최고·최저를 잡으면 하락 추세 전체가
    박스가 되어버리므로 (1) 폭 제한과 (2) 바닥 이탈 시 무효 규칙을 함께 적용한다.
    가장 최근에 확정된 박스를 쓰기 위해 오른쪽부터 훑는다.
    """
    out = {"box_top": None, "box_bottom": None, "box_bars": 0,
           "box_ready": False, "box_breakout": False}
    n = len(high)
    if n < window + confirm + 2:
        return out

    price = float(close[-1])

    for t in range(n - confirm - 2, max(n - window, confirm) - 1, -1):
        # 천장 후보는 직전 구간의 신고가여야 한다 (Darvas는 신고가에서만 박스를 그린다)
        if high[t] < high[max(0, t - window):t].max():
            continue
        if high[t + 1: t + 1 + confirm].max() >= high[t]:
            continue                                   # confirm봉 내 경신 → 천장 아님
        top = float(high[t])

        after_low = low[t + 1:]
        if len(after_low) < confirm + 1:
            continue
        b = int(after_low.argmin())
        if b + confirm >= len(after_low):
            continue                                   # 바닥이 아직 confirm봉을 못 버팀
        if after_low[b + 1: b + 1 + confirm].min() <= after_low[b]:
            continue
        bottom = float(after_low[b])
        if bottom <= 0 or top <= bottom:
            continue

        if (top - bottom) / bottom > max_width:
            continue                                   # 횡보가 아니라 추세 구간
        if price < bottom:
            continue                                   # 바닥 이탈 = 박스 무효

        out["box_top"] = top
        out["box_bottom"] = bottom
        out["box_bars"] = n - t
        out["box_ready"] = True
        out["box_breakout"] = bool(price > top)
        return out

    return out


def trading_range(high: np.ndarray, low: np.ndarray,
                  min_bars: int = BASE_MIN_BARS, max_bars: int = BASE_WINDOW,
                  max_width: float = BASE_MAX_WIDTH, exclude: int = BASE_EXCLUDE) -> dict:
    """
    직전 횡보 구간(Stage 1 베이스 / Wyckoff 거래범위)의 상단·하단.

    고정 구간의 최고·최저를 쓰면 추세 구간까지 '베이스'가 되어 저항선이 무의미해진다.
    끝에서부터 구간을 넓히다가 폭 제한을 넘는 순간 멈춰, 실제로 횡보한 만큼만 잡는다.
    돌파 직전 봉은 제외해야 돌파 자체가 저항선이 되지 않는다.
    """
    out = {"range_high": None, "range_low": None, "range_width": None, "range_bars": 0}
    n = len(high)
    if n < min_bars + exclude:
        return out

    h = high[: n - exclude]
    l = low[: n - exclude]

    hi, lo, best = -np.inf, np.inf, None
    for k in range(1, min(max_bars, len(h)) + 1):
        hi = max(hi, float(h[-k]))
        lo = min(lo, float(l[-k]))
        if lo <= 0:
            break
        if (hi - lo) / lo > max_width:
            break
        if k >= min_bars:
            best = (hi, lo, k)

    if best is None:
        return out

    hi, lo, k = best
    out["range_high"]  = hi
    out["range_low"]   = lo
    out["range_width"] = round((hi - lo) / lo, 4)
    out["range_bars"]  = k
    return out


def wyckoff_state(high, low, close, volume, rng: dict) -> dict:
    """
    Wyckoff 매집의 '구조적으로 확인 가능한 부분'만 잡는다.
    국면(A~E) 판정과 SC/AR/ST 식별은 거래량-스프레드 재량 해석이라 코드로 옮기지 않았다.

      Spring : 거래범위 하단을 잠깐 이탈했다가 회복 (하락 함정)
      SOS    : 거래량을 동반한 상단 돌파
      매집   : 하락일 거래량 < 상승일 거래량 (매도 압력 소진)
    """
    out = {"spring": False, "sos": False, "vol_dry_down": False, "in_range": False}
    if rng.get("range_high") is None:
        return out

    hi, lo = rng["range_high"], rng["range_low"]
    price = float(close[-1])
    out["in_range"] = bool(lo <= price <= hi)

    look = min(30, len(low))
    seg_l, seg_c = low[-look:], close[-look:]
    # 저가는 하단을 깼는데 종가는 되돌아온 봉이 있으면 Spring
    out["spring"] = bool(((seg_l < lo) & (seg_c > lo)).any())

    vol20 = float(volume[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
    out["sos"] = bool(price > hi and vol20 > 0 and float(volume[-1]) / vol20 >= 2.0)

    # 매집 구간에서는 하락일 거래량이 상승일보다 작다
    look2 = min(40, len(close) - 1)
    if look2 > 5:
        diff = np.diff(close[-(look2 + 1):])
        v = volume[-look2:]
        up, dn = v[diff > 0], v[diff < 0]
        if len(up) and len(dn):
            out["vol_dry_down"] = bool(dn.mean() < up.mean())
    return out


def rs_strength(close: pd.Series, bars_per_year: int = 252) -> float | None:
    """
    IBD RS Rating의 원재료 — 분기별 가중 수익률.
    0.4×ROC(1분기) + 0.2×ROC(2분기) + 0.2×ROC(3분기) + 0.2×ROC(4분기)
    이 값을 유니버스 전체에서 백분위로 환산해야 비로소 RS Rating(1~99)이 된다.
    """
    q = max(1, bars_per_year // 4)
    spans = [(q, 0.4), (q * 2, 0.2), (q * 3, 0.2), (q * 4, 0.2)]
    if len(close) <= spans[-1][0]:
        return None

    now = float(close.iloc[-1])
    total = 0.0
    for bars, w in spans:
        ref = float(close.iloc[-bars - 1])
        if ref <= 0:
            return None
        total += w * (now - ref) / ref
    return round(total, 6)
