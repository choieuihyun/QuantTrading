"""
과거 시점 재현 — "그날 이 패턴 리스트 상위 N종목을 샀으면 얼마 벌었나"

기존 backtest.py는 '신호가 뜬 종목 전부'를 사는 가정이라 화면에 뜨는 상위 N개 리스트의
성과와 다르다. 여기서는 매 스캔일마다 유니버스 전체를 스코어링해 상위 N개를 뽑고,
그 묶음을 동일가중으로 산 결과를 벤치마크 대비로 측정한다.

2단계 구조 — 신호 계산이 느리고 패턴/보유일/상위N은 그 뒤에 붙는 값이라 분리했다.
  1) build : 종목×날짜 신호 + 미래수익률 → parquet 적재 (느림, 1회)
  2) eval  : 조건을 바꿔가며 즉시 집계 (빠름, 반복)

사용:
  python replay.py build --market kr --days 1100
  python replay.py eval  --market kr --hold 20 --top 30
  python replay.py eval  --market kr --pattern wyckoff --hold 60 --top 10
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import FinanceDataReader as fdr

from screener import (
    calc_signals_from_df, drop_partial_bar, sanitize_ohlc, get_universe, score_pattern,
    attach_rs_rating,
    ALL_PATTERN_KEYS, TREND_PATTERN_KEYS, ACCUM_PATTERN_KEYS, CUSTOM_PATTERN_KEYS,
    SCORE_THRESHOLD, _last_weekday,
)
from market_config import ALL_CONFIGS

CACHE_DIR = Path(__file__).parent / ".cache"
HORIZONS  = [5, 20, 60]
STOP_KEY  = {5: "stop_swing", 20: "stop_swing", 60: "stop_lt"}

# 공통 카테고리 — 구성 패턴 중 몇 개 이상이면 편입인지
# 구성 패턴이 1개뿐인 카테고리에 "2개 이상"을 요구하면 영원히 비어 있게 된다
COMMON_SPECS = {
    "common_trend": (TREND_PATTERN_KEYS,  min(2, len(TREND_PATTERN_KEYS))),
    "common_accum": (ACCUM_PATTERN_KEYS,  min(2, len(ACCUM_PATTERN_KEYS))),
    "common_all":   (CUSTOM_PATTERN_KEYS, min(2, len(CUSTOM_PATTERN_KEYS))),
}
EVAL_KEYS = ALL_PATTERN_KEYS + list(COMMON_SPECS)


# ══════════════════════════════════════════════════════
# 1단계: 패널 적재
# ══════════════════════════════════════════════════════

def pit_universe(cfg: dict, start_date: str) -> pd.DataFrame:
    """
    상장폐지 종목까지 포함한 유니버스 — 오늘 살아남은 종목만 보면 망한 종목이
    표본에서 통째로 빠져 성과가 부풀려진다(생존편향).

    시총 필터는 적용하지 않는다. 과거 시점의 시총을 알 수 없어 오늘 시총으로 거르면
    미래 정보가 새어든다. 유동성은 avg_value_20(시점별 계산)이 _base_ok에서 거른다.
    """
    live = pd.DataFrame(get_universe({**cfg, "min_marcap": None}))
    live["delisted"] = False

    if cfg["type"] != "KR":
        return live  # 미장/코인은 폐지 종목 소스가 없음 — 생존편향 잔존

    try:
        dl = fdr.StockListing("KRX-DELISTING")
    except Exception as e:
        print(f"  ⚠ 폐지 종목 조회 실패 ({e}) — 생존편향이 남습니다")
        return live

    dl = dl.rename(columns={"Symbol": "ticker", "Name": "name", "Market": "market"})
    dl["DelistingDate"] = pd.to_datetime(dl["DelistingDate"], errors="coerce")
    dl = dl[
        (dl["SecuGroup"] == "주권")
        & dl["market"].isin(cfg["markets"])
        & (dl["DelistingDate"] >= pd.Timestamp(start_date))
    ]

    # 살아있는 종목과 동일한 필터를 폐지 종목에도 적용
    if cfg.get("common_stock_only"):
        dl = dl[dl["ticker"].astype(str).str.endswith("0")]
    pattern = cfg.get("exclude_name_patterns")
    if pattern:
        dl = dl[~dl["name"].astype(str).str.contains(pattern, na=False)]

    dl = dl[["ticker", "name", "market"]].copy()
    dl["sector"] = ""
    dl["marcap"] = None
    dl["delisted"] = True
    dl = dl[~dl["ticker"].isin(set(live["ticker"]))]

    print(f"  폐지 종목 {len(dl)}개 추가 (생존편향 보정)")
    return pd.concat([live, dl], ignore_index=True)


def _cache_path(market_key: str, ticker: str) -> Path:
    d = CACHE_DIR / market_key
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{str(ticker).replace('/', '_')}.parquet"


def _load_history(market_key: str, ticker: str, start_date: str, max_date: pd.Timestamp,
                  cfg: dict, delisted: bool = False) -> pd.DataFrame | None:
    """디스크 캐시 — 재현을 조건 바꿔가며 돌릴 때 매번 받으면 이것만 수십 분 걸린다"""
    path = _cache_path(market_key, ticker)
    if path.exists():
        try:
            df = pd.read_parquet(path)
            covers_start = df.index[0] <= pd.Timestamp(start_date) + pd.Timedelta(days=10)
            # 폐지 종목은 마지막 봉이 과거에 멈춰 있는 게 정상 — 최신성 검사에서 제외
            is_fresh = delisted or df.index[-1] >= max_date - pd.Timedelta(days=5)
            if len(df) and covers_start and is_fresh:
                return sanitize_ohlc(df)   # 캐시는 정제 전에 저장된 것일 수 있음
        except Exception:
            pass

    try:
        df = fdr.DataReader(ticker, start_date)
    except Exception:
        return None
    if df is None or df.empty:
        return None

    df = drop_partial_bar(df, cfg)
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df = sanitize_ohlc(df)
    try:
        df.to_parquet(path)
    except Exception:
        pass
    return df


def _forward_outcomes(hist: pd.DataFrame, i: int, signals: dict, cfg: dict,
                      still_listed: bool) -> dict | None:
    """
    진입은 신호 다음날 시가. 신호는 종가가 확정돼야 알 수 있는데 당일 종가로 사면
    그날의 거래량 급등에 따라붙는 갭상승을 공짜로 먹는 셈이 된다.

    보유 기간이 데이터 끝을 넘어가는 경우가 두 가지인데 처리가 정반대다.
      - 상장폐지: 마지막 체결가로 청산. 버리면 생존편향이 되돌아온다.
      - 패널 우측 끝(아직 미래가 없음): 기록하지 않는다. 60일 보유를 3일로 재게 된다.
    """
    n = len(hist)
    if i + 1 >= n:
        return None

    opens  = hist["Open"].to_numpy()
    lows   = hist["Low"].to_numpy()
    closes = hist["Close"].to_numpy()

    entry = float(opens[i + 1])
    if not np.isfinite(entry) or entry <= 0:
        return None

    out = {"entry_price": entry}
    for h in HORIZONS:
        target = i + h
        overrun = target >= n
        if overrun and still_listed:
            continue
        exit_i = min(target, n - 1)
        if exit_i <= i:
            continue

        stop = float(signals[STOP_KEY[h]])
        seg  = lows[i + 1 : exit_i + 1]
        hit  = np.flatnonzero(seg <= stop)
        if hit.size:
            j = i + 1 + int(hit[0])
            exit_price, stopped = min(stop, float(opens[j])), True
        else:
            exit_price, stopped = float(closes[exit_i]), False

        out[f"ret_{h}"]   = round(_net_return(entry, exit_price, cfg), 5)
        out[f"stop_{h}"]  = stopped
        out[f"trunc_{h}"] = overrun
        # 손절 없이 만기 보유했을 때 — 손절이 성과를 깎는지 패턴 자체가 부진한지 분리
        out[f"raw_{h}"]   = round(_net_return(entry, float(closes[exit_i]), cfg), 5)

    # 안 팔고 지금까지 들고 있으면 — "그날 리스트를 샀으면 현재 얼마"에 답하는 값.
    # 고정 보유기간과 달리 날짜마다 보유일이 다르므로 patterns 간 비교가 아니라 실제 손익 확인용.
    last_close = float(closes[-1])
    out["ret_now"]    = round(_net_return(entry, last_close, cfg), 5)
    out["held_bars"]  = int(n - 1 - (i + 1))
    out["last_close"] = last_close
    # 폐지 종목은 여기서 시계열이 끝난다 — 벤치마크도 같은 날까지만 재야 비교가 성립
    out["last_date"]  = hist.index[-1]
    # 보유 중 ATR 손절선을 건드린 적이 있는지 (참고용 — 청산은 하지 않음)
    seg_all = lows[i + 1 :]
    out["touched_stop"] = bool((seg_all <= float(signals["stop_swing"])).any())
    return out


def _net_return(entry: float, exit_price: float, cfg: dict) -> float:
    buy_cost  = cfg.get("fee_rate", 0.0) + cfg.get("slippage", 0.0)
    sell_cost = cfg.get("fee_rate", 0.0) + cfg.get("slippage", 0.0) + cfg.get("tax_rate", 0.0)
    eff_entry = entry * (1 + buy_cost)
    eff_exit  = exit_price * (1 - sell_cost)
    return (eff_exit - eff_entry) / eff_entry


def _scan_ticker(row: dict, hist: pd.DataFrame, scan_dates: pd.DatetimeIndex,
                 bench_ret: pd.Series, cfg: dict, still_listed: bool,
                 bench_up: pd.Series = None) -> list[dict]:
    lookback = cfg.get("lookback_bars", 300)
    min_value = cfg.get("min_trading_value") or 0

    # _base_ok과 같은 유동성 게이트를 미리 벡터로 계산 — 통과 못 할 날은 신호 계산 자체를 건너뛴다
    value_20 = (hist["Close"] * hist["Volume"]).rolling(20).mean().to_numpy()

    positions = hist.index.get_indexer(scan_dates)
    rows = []
    for pos in positions:
        if pos < lookback or pos + 1 >= len(hist):
            continue
        if not np.isfinite(value_20[pos]) or value_20[pos] < min_value:
            continue

        date = hist.index[pos]
        mr = bench_ret.get(date)
        if mr is None or not np.isfinite(mr):
            continue

        up = True if bench_up is None else bool(bench_up.get(date, True))
        window  = hist.iloc[pos + 1 - lookback : pos + 1]
        signals = calc_signals_from_df(window, market_return=float(mr), cfg=cfg,
                                       market_uptrend=up)
        if signals is None:
            continue

        fwd = _forward_outcomes(hist, pos, signals, cfg, still_listed)
        if fwd is None:
            continue

        rows.append({
            "ticker": row["ticker"], "name": row["name"], "market": row["market"],
            "date": date, **signals, **fwd,
        })
    return rows


def build(market_key: str, days: int, scan_interval: int, sample: int | None) -> Path:
    cfg = ALL_CONFIGS[market_key]
    start_date = _last_weekday(datetime.today() - timedelta(days=days),
                               skip_weekends=cfg.get("skip_weekends", True))

    print(f"\n=== {cfg['name']} 재현 패널 적재 ({start_date} ~) ===")

    bench_raw = fdr.DataReader(cfg["benchmark"], start_date)
    if bench_raw.empty:
        raise RuntimeError(f"벤치마크 {cfg['benchmark']} 데이터 없음")
    bench = bench_raw[["Open", "Close"]].astype(float)
    max_date = bench.index[-1]

    # 신호 시점의 시장 3개월 수익률 — rs를 라이브와 동일 정의로 계산
    mbars = 65 if cfg["type"] != "CRYPTO" else 90
    bench_ret = (bench["Close"] / bench["Close"].shift(mbars) - 1).round(4)

    # CAN SLIM의 M — 각 스캔일 시점의 시장 방향 (그날까지의 데이터만 사용)
    bc = bench["Close"]
    bma200 = bc.rolling(200).mean()
    bench_up = (bc > bma200) & (bma200 > bma200.shift(21))

    universe = pit_universe(cfg, start_date)
    if sample:
        universe = universe.sample(min(sample, len(universe)), random_state=42)
    print(f"  유니버스 {len(universe)}종목 (시총 필터 미적용 — 유동성은 시점별로 판정)")

    lookback = cfg.get("lookback_bars", 300)
    scan_dates = bench.index[lookback::scan_interval]
    print(f"  스캔일 {len(scan_dates)}일 (간격 {scan_interval}봉)")

    records = universe.to_dict("records")

    def work(row):
        hist = _load_history(market_key, row["ticker"], start_date, max_date, cfg,
                             delisted=bool(row.get("delisted")))
        if hist is None or len(hist) <= lookback:
            return []
        still_listed = hist.index[-1] >= max_date - pd.Timedelta(days=5)
        return _scan_ticker(row, hist, scan_dates, bench_ret, cfg, still_listed, bench_up)

    all_rows, done = [], 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for res in ex.map(work, records):
            all_rows.extend(res)
            done += 1
            if done % 200 == 0:
                print(f"  진행 {done}/{len(records)} — 누적 {len(all_rows)}행")

    if not all_rows:
        raise RuntimeError("적재된 행이 없습니다 — 기간/유니버스 확인 필요")

    panel = pd.DataFrame(all_rows)

    # RS Rating은 날짜별 유니버스 백분위 — 라이브가 거래가능 종목을 모집단으로 쓰므로 동일하게 맞춘다
    panel = (panel[panel["is_tradable"]]
             .groupby("date", group_keys=False)
             .apply(attach_rs_rating, include_groups=True)
             .reset_index(drop=True))

    # 벤치마크 수익률을 동일 창(다음날 시가 → h일 뒤 종가)으로 붙여 초과수익을 비교 가능하게 만듦
    bidx = bench.index
    bpos = bidx.get_indexer(panel["date"])
    b_open, b_close = bench["Open"].to_numpy(), bench["Close"].to_numpy()
    entry_i = np.clip(bpos + 1, 0, len(bidx) - 1)
    for h in HORIZONS:
        exit_i = np.clip(bpos + h, 0, len(bidx) - 1)
        panel[f"bench_{h}"] = np.round(b_close[exit_i] / b_open[entry_i] - 1, 5)

    # 현재까지 보유 시의 벤치마크 — 폐지 종목은 그 종목이 끝난 날까지만 잰다
    last_i = np.clip(bidx.get_indexer(panel["last_date"], method="ffill"), 0, len(bidx) - 1)
    panel["bench_now"] = np.round(b_close[last_i] / b_open[entry_i] - 1, 5)

    out = CACHE_DIR / f"panel_{market_key}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(out)

    n_del = panel["ticker"].nunique()
    print(f"\n적재 완료: {len(panel):,}행 / {n_del}종목 / {panel['date'].nunique()}일 → {out}")
    return out


# ══════════════════════════════════════════════════════
# 2단계: 조건별 집계
# ══════════════════════════════════════════════════════

def _attach_scores(panel: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """cfg 임계값을 바꿔가며 재평가할 수 있도록 조회 시점에 스코어를 계산한다"""
    signal_rows = panel.to_dict("records")
    for key in ALL_PATTERN_KEYS:
        panel[f"score_{key}"] = [score_pattern(key, s, cfg) for s in signal_rows]

    threshold = cfg.get("score_threshold", SCORE_THRESHOLD)
    for name, (members, min_hits) in COMMON_SPECS.items():
        hits = sum((panel[f"score_{k}"] >= threshold).astype(int) for k in members)
        panel[f"hits_{name}"]  = hits
        panel[f"score_{name}"] = sum(panel[f"score_{k}"] for k in members) / len(members)
    return panel


TIE_SEED = 7


def _select(panel: pd.DataFrame, key: str, top_k: int, threshold: float) -> pd.DataFrame:
    """
    매 스캔일마다 화면에 떴을 리스트를 그대로 재현 — 스코어 상위 N종목.

    동점 처리를 행 순서에 맡기면 안 된다. 게이트만 넘으면 만점이 되는 패턴은 상위 N이
    전부 동점이라 순위가 사실상 적재 순서(=종목코드 순)로 정해지고, 대형주가 앞에 몰린
    구간에서는 없는 선정력이 있는 것처럼 보인다. 고정 시드 난수로 동점을 깬다.
    """
    if key in COMMON_SPECS:
        _, min_hits = COMMON_SPECS[key]
        elig = panel[panel[f"hits_{key}"] >= min_hits]
    else:
        elig = panel[panel[f"score_{key}"] >= threshold]
    if elig.empty:
        return elig

    elig = elig.copy()
    jitter = np.random.default_rng(TIE_SEED).random(len(elig))
    elig["_tie"] = elig[f"score_{key}"] + jitter * 1e-6
    elig["rank"] = elig.groupby("date")["_tie"].rank(ascending=False, method="first")
    return elig[elig["rank"] <= top_k]


def _tie_ratio(sel: pd.DataFrame, key: str) -> float:
    """상위 N이 동점으로만 채워진 날의 비율 — 높으면 스코어 정렬에 정보가 없다는 뜻"""
    g = sel.groupby("date")[f"score_{key}"].nunique()
    return round(float((g <= 1).mean()), 4) if len(g) else 0.0


def _rank_ic(sel: pd.DataFrame, key: str, ret_col: str) -> float | None:
    """
    스코어 순위가 실제 수익률 순위를 맞추는지 — 날짜별 상관의 평균.
    순위로 바꾼 뒤 피어슨을 쓰면 스피어만과 같아서 scipy 없이 계산된다.
    """
    ics = []
    for _, g in sel.groupby("date"):
        g = g.dropna(subset=[ret_col])
        # 그날 상위 종목 점수가 전부 같으면 순위 자체가 정의되지 않는다 (게이트만 넘으면
        # 만점이 되는 패턴에서 흔함) — 상관이 아니라 변별력 부재이므로 표본에서 뺀다
        if len(g) < 5 or g[f"score_{key}"].nunique() < 2:
            continue
        ic = g[f"score_{key}"].rank().corr(g[ret_col].rank())
        if pd.notna(ic):
            ics.append(ic)
    return round(float(np.mean(ics)), 4) if ics else None


def evaluate(panel: pd.DataFrame, key: str, hold: int, top_k: int,
             threshold: float, no_stop: bool = False) -> dict:
    ret_col  = f"raw_{hold}" if no_stop else f"ret_{hold}"
    bench_col = f"bench_{hold}"
    sel = _select(panel, key, top_k, threshold)
    sel = sel.dropna(subset=[ret_col]) if not sel.empty else sel
    if sel.empty:
        return {"pattern": key, "hold": hold, "top_k": top_k, "n_dates": 0, "n_picks": 0,
                "no_stop": no_stop}

    # 날짜별 동일가중 포트폴리오 — 리스트를 통째로 산 결과
    per_date = sel.groupby("date").agg(
        port=(ret_col, "mean"),
        bench=(bench_col, "mean"),
        n=(ret_col, "size"),
    )
    # 지수는 시총가중이라 대형주 몇 개가 끌어올린 장에서는 동일가중 포트폴리오가 구조적으로 뒤진다.
    # 그날 유동성을 통과한 전 종목의 동일가중 평균을 같이 둬야 '종목을 잘 골랐는지'가 분리된다.
    # 거래정지·가격고정 종목은 애초에 선정 대상이 아니므로 기준선에서도 뺀다.
    universe = panel[panel["is_tradable"]].groupby("date")[ret_col].mean()
    per_date["uni"] = universe.reindex(per_date.index)
    per_date["excess"]     = per_date["port"] - per_date["bench"]
    per_date["excess_uni"] = per_date["port"] - per_date["uni"]

    # 순위 구간별 성과는 유니버스 평균 대비로 본다 — 같은 날 전 구간이 같은 지수를 빼면
    # 구간 간 비교에서 지수가 상수로 남아 차이가 묻힌다
    uni_by_row = sel["date"].map(universe)
    buckets = {}
    for lo, hi in [(1, 10), (11, 20), (21, 30)]:
        if lo > top_k:
            continue
        mask = (sel["rank"] >= lo) & (sel["rank"] <= hi)
        if mask.any():
            buckets[f"{lo}-{min(hi, top_k)}위"] = round(
                float((sel.loc[mask, ret_col] - uni_by_row[mask]).mean()), 4)

    stat = {
        "pattern":     key,
        "hold":        hold,
        "top_k":       top_k,
        "threshold":   threshold,
        "no_stop":     no_stop,
        "n_dates":     int(len(per_date)),
        "n_picks":     int(len(sel)),
        "avg_picks_per_date": round(float(per_date["n"].mean()), 1),
        # 리스트를 산 결과 (날짜 평균)
        "port_return":   round(float(per_date["port"].mean()), 4),
        "bench_return":  round(float(per_date["bench"].mean()), 4),
        "uni_return":    round(float(per_date["uni"].mean()), 4),
        "excess_return": round(float(per_date["excess"].mean()), 4),
        "excess_median": round(float(per_date["excess"].median()), 4),
        # 종목 선정 실력 — 지수(시총가중)가 아니라 그날 유동성 통과 종목 평균 대비
        "excess_uni":    round(float(per_date["excess_uni"].mean()), 4),
        "uni_hit_rate":  round(float((per_date["excess_uni"] > 0).mean()), 4),
        # 날짜 단위 승률 — 종목 단위로 세면 같은 날 30종목이 30표가 되어 과대평가된다
        "date_hit_rate": round(float((per_date["excess"] > 0).mean()), 4),
        "name_hit_rate": round(float((sel[ret_col] > 0).mean()), 4),
        "best_date":  str(per_date["excess"].idxmax())[:10],
        "worst_date": str(per_date["excess"].idxmin())[:10],
        "worst_excess": round(float(per_date["excess"].min()), 4),
        "stop_hit_rate": round(float(sel[f"stop_{hold}"].mean()), 4),
        "delisted_exits": int(sel[f"trunc_{hold}"].sum()),
        "rank_buckets": buckets,
        "rank_ic": _rank_ic(sel, key, ret_col),
        "tie_ratio": _tie_ratio(sel, key),
    }
    return stat


def _fmt(stat: dict) -> str:
    if not stat.get("n_dates"):
        return f"  {stat['pattern']:14} 신호 없음"
    ic = stat["rank_ic"]
    return (f"  {stat['pattern']:14} "
            f"{stat['port_return']*100:+6.2f}% "
            f"{stat['uni_return']*100:+6.2f}% "
            f"{stat['excess_uni']*100:+6.2f}% "
            f"{stat['uni_hit_rate']*100:5.0f}% "
            f"{stat['excess_return']*100:+7.2f}% "
            f"{stat['n_dates']:>5} "
            f"{stat['avg_picks_per_date']:>6.1f} "
            f"{'  n/a' if ic is None else f'{ic:+.3f}'} "
            f"{stat['tie_ratio']*100:>5.0f}%")


def report(market_key: str, hold: int, top_k: int, patterns: list[str],
           threshold: float | None, no_stop: bool = False) -> list[dict]:
    cfg = ALL_CONFIGS[market_key]
    thr = threshold if threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)

    path = CACHE_DIR / f"panel_{market_key}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — 먼저 실행: python replay.py build --market {market_key}")

    panel = pd.read_parquet(path)
    panel = _attach_scores(panel, {**cfg, "score_threshold": thr})

    span = f"{str(panel['date'].min())[:10]} ~ {str(panel['date'].max())[:10]}"
    mode = " | 손절 미적용(만기보유)" if no_stop else ""
    print(f"\n=== {cfg['name']} | 보유 {hold}일 | 상위 {top_k}종목 | 임계 {thr}점{mode} ===")
    print(f"기간 {span} | 패널 {len(panel):,}행")
    print(f"\n  {'패턴':14} {'리스트':>7} {'유니버스':>7} {'선정력':>7} {'승률':>6} "
          f"{'vs지수':>8} {'날짜':>5} {'종목':>6} {'RankIC':>7} {'동점':>5}")
    print("  " + "─" * 89)

    stats = []
    for key in patterns:
        s = evaluate(panel, key, hold, top_k, thr, no_stop=no_stop)
        stats.append(s)
        print(_fmt(s))

    print("\n  * 리스트 = 스캔일마다 상위 N종목 동일가중 매수 후 평균 (비용 반영)")
    print("  * 유니버스 = 그날 유동성 통과 전 종목 동일가중 평균 | 선정력 = 리스트 − 유니버스")
    print("  * vs지수 = 리스트 − 벤치마크. 지수는 시총가중이라 대형주 장세에서 구조적으로 불리")
    print("  * 승률 = 유니버스 평균을 이긴 '날짜' 비율 | RankIC = 스코어 순위와 수익률 순위 상관")
    print("  * 동점 = 상위 N이 전부 같은 점수였던 날의 비율. 높으면 순위·RankIC가 무의미")
    print(f"  * 보유 {hold}일 구간이 겹치므로 날짜 수만큼 독립 관측이 아님 — 유의성 판단 금물")

    # 순위 구간별 성과 — 스코어 정렬이 정보를 담고 있는지 직접 확인
    print(f"\n  [순위 구간별 초과수익 — 유니버스 평균 대비]")
    for s in stats:
        if s.get("rank_buckets"):
            parts = " ".join(f"{k} {v*100:+.2f}%" for k, v in s["rank_buckets"].items())
            print(f"  {s['pattern']:14} {parts}")

    return stats


def picks(market_key: str, key: str, hold: int | None, top_k: int, date: str | None,
          threshold: float | None, no_stop: bool = False) -> pd.DataFrame:
    """
    특정 스캔일에 그 패턴 리스트에 무엇이 떴고 종목별로 얼마가 났는지.

    hold=None이면 '안 팔고 지금까지' 기준(ret_now) — 그날 샀으면 현재 얼마인지.
    hold를 주면 고정 보유기간(그날 사서 N거래일 뒤 매도) 기준.
    """
    cfg = ALL_CONFIGS[market_key]
    thr = threshold if threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)
    if hold is None:
        ret_col, bench_col = "ret_now", "bench_now"
    else:
        ret_col, bench_col = (f"raw_{hold}" if no_stop else f"ret_{hold}"), f"bench_{hold}"

    path = CACHE_DIR / f"panel_{market_key}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — 먼저 실행: python replay.py build --market {market_key}")

    panel = _attach_scores(pd.read_parquet(path), {**cfg, "score_threshold": thr})
    available = sorted(panel["date"].unique())

    if date:
        target = pd.Timestamp(date)
        # 정확히 그날이 스캔일이 아닐 수 있으므로 이전 스캔일로 맞춘다
        prior = [d for d in available if d <= target]
        if not prior:
            raise SystemExit(f"{date} 이전 스캔일이 없습니다 (최초 {str(available[0])[:10]})")
        target = prior[-1]
    else:
        target = available[-1]

    sel = _select(panel, key, top_k, thr)
    sel = sel[sel["date"] == target].sort_values("rank")
    if sel.empty:
        print(f"{str(target)[:10]} · {key}: 해당 조건에 뜬 종목 없음")
        return sel

    sel = sel.dropna(subset=[ret_col])
    if sel.empty:
        print(f"{str(target)[:10]} · {key}: 아직 보유기간이 지나지 않았습니다")
        return sel

    uni = panel[(panel["date"] == target) & panel["is_tradable"]][ret_col].mean()
    bench = float(sel[bench_col].iloc[0])

    cols = ["rank", "ticker", "name", "price", "entry_price", f"score_{key}", ret_col]
    labels = ["순위", "종목코드", "종목명", "신호일종가", "매수가", "점수", "수익률"]
    if hold is None:
        cols += ["last_close", "held_bars", "touched_stop"]
        labels += ["현재가", "보유일", "손절선터치"]
    else:
        cols += [f"stop_{hold}", f"trunc_{hold}"]
        labels += ["손절청산", "폐지청산"]

    view = sel[cols].copy()
    view.columns = labels
    view["수익률"] = (view["수익률"] * 100).round(2)
    view["점수"] = view["점수"].round(0)

    if hold is None:
        title = f"안 팔고 현재까지 보유 (기준일 종가 {str(panel['date'].max())[:10]})"
    else:
        title = f"{hold}거래일 보유 후 매도" + (" · 손절 미적용" if no_stop else "")
    print(f"\n=== {str(target)[:10]} 진입 · {key} · 상위 {top_k} · {title} ===")
    print(view.to_string(index=False))

    port = float(sel[ret_col].mean())
    wins = int((sel[ret_col] > 0).sum())
    print(f"\n  리스트 평균 {port*100:+.2f}%  |  플러스 {wins}/{len(sel)}종목")
    if pd.notna(uni):
        print(f"  유니버스 평균 {uni*100:+.2f}%  →  선정력 {(port-uni)*100:+.2f}%p")
    print(f"  KOSPI {bench*100:+.2f}%  →  초과 {(port-bench)*100:+.2f}%p")
    return view


PICK_DATES = 40   # 화면에서 고를 수 있는 최근 스캔일 수

# "지금까지 보유"(now)가 기본 — 실제로 보고 판단할 때 궁금한 건 현재 손익이다.
# 고정 보유기간은 패턴끼리 공정 비교할 때 쓴다(날짜마다 보유일이 달라지지 않으므로).
RET_COLS = ["ret_now"] + [f"ret_{h}" for h in HORIZONS]


def build_picks_docs(market_key: str, top_k: int = 30, threshold: float | None = None,
                     n_dates: int = PICK_DATES) -> tuple[list[dict], dict]:
    """
    날짜별 '그날 리스트에 뭐가 떴고 각각 얼마 났는지'를 화면용 문서로 만든다.

    집계 그리드(build_grid)는 평균만 알려줘서 실제 투자 판단에는 부족하다.
    종목을 직접 보고 고르려면 개별 행이 필요하다. 전 기간을 한 문서에 담으면 1MB를
    넘으므로 날짜당 한 문서로 쪼갠다.
    """
    cfg = ALL_CONFIGS[market_key]
    thr = threshold if threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)

    path = CACHE_DIR / f"panel_{market_key}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — 먼저 실행: python replay.py build --market {market_key}")

    panel = _attach_scores(pd.read_parquet(path), {**cfg, "score_threshold": thr})
    dates = sorted(panel["date"].unique())[-n_dates:]

    # 패턴별 선정을 전 기간에 대해 한 번만 계산하고 날짜로 잘라 쓴다
    selections = {k: _select(panel, k, top_k, thr) for k in EVAL_KEYS}
    liquid = panel[panel["is_tradable"]]
    uni_by_date = {c: liquid.groupby("date")[c].mean() for c in RET_COLS}

    docs = []
    for d in dates:
        day = {}
        for key in EVAL_KEYS:
            sel = selections[key]
            rows = sel[sel["date"] == d].sort_values("rank")
            if rows.empty:
                continue

            picks_out = []
            for _, r in rows.iterrows():
                item = {
                    "rank":   int(r["rank"]),
                    "ticker": str(r["ticker"]),
                    "name":   str(r["name"]),
                    "score":  round(float(r[f"score_{key}"]), 1),
                    "price":  float(r["price"]),
                    "entry":  float(r["entry_price"]),
                    "rsi":    float(r["rsi"]),
                    "vol_ratio": float(r["vol_ratio"]),
                    "pos_52w":   float(r["pos_52w"]),
                    "stop_swing": float(r["stop_swing"]),
                    # 안 팔고 지금까지 — 화면 기본값
                    "ret_now":    round(float(r["ret_now"]), 4),
                    "last_close": float(r["last_close"]),
                    "held_bars":  int(r["held_bars"]),
                    "touched_stop": bool(r["touched_stop"]),
                }
                for h in HORIZONS:
                    v = r.get(f"ret_{h}")
                    # 아직 보유기간이 안 지난 최근 날짜는 값이 없다 — 화면에서 '진행 중'으로 표시
                    item[f"ret_{h}"]  = None if pd.isna(v) else round(float(v), 4)
                    item[f"stop_{h}"] = None if pd.isna(v) else bool(r[f"stop_{h}"])
                picks_out.append(item)

            summary = {}
            for col in RET_COLS:
                valid = rows[col].dropna()
                slot = "now" if col == "ret_now" else col.split("_")[1]
                if valid.empty:
                    summary[slot] = {"n": 0}
                    continue
                uni = uni_by_date[col].get(d)
                bench_col = "bench_now" if col == "ret_now" else f"bench_{slot}"
                summary[slot] = {
                    "n":     int(len(valid)),
                    "port":  round(float(valid.mean()), 4),
                    "uni":   None if pd.isna(uni) else round(float(uni), 4),
                    "bench": round(float(rows[bench_col].iloc[0]), 4),
                    "wins":  int((valid > 0).sum()),
                }
            day[key] = {"summary": summary, "picks": picks_out}

        if day:
            docs.append({
                "market": market_key,
                "date":   str(d)[:10],
                "top_k":  top_k,
                "threshold": thr,
                "patterns": day,
            })

    # 각 날짜가 지금으로부터 몇 거래일 전인지 — 화면의 "N일 전" 선택에 쓴다.
    # 패널의 전체 스캔일이 아니라 종목 시계열 기준이어야 정확하므로 held_bars의 최빈값을 쓴다.
    latest = panel["date"].max()
    bars_ago = {}
    for d in dates:
        rows = panel[panel["date"] == d]
        bars_ago[str(d)[:10]] = int(rows["held_bars"].max()) + 1 if len(rows) else 0

    index = {
        "market":       market_key,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "top_k":        top_k,
        "threshold":    thr,
        "holds":        HORIZONS,
        "dates":        [{"date": d["date"], "bars_ago": bars_ago[d["date"]]} for d in docs],
        "latest_bar":   str(latest)[:10],
    }
    return docs, index


GRID_TOPS = [10, 20, 30]


def _differs(a, b) -> bool:
    """
    불리언·정수는 정확히 일치해야 한다 — 게이트를 직접 좌우한다.
    실수는 MACD의 EWM 초기화 잔차가 반올림 자리에서 드러나므로 상대오차로 본다.
    """
    if isinstance(a, bool) or isinstance(b, bool):
        return a != b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) > 1e-4 * max(1.0, abs(a), abs(b))
    return a != b


def build_grid(market_key: str, threshold: float | None = None) -> dict:
    """대시보드에서 보유일·상위N을 바꿔가며 볼 수 있도록 조합을 미리 계산해 둔다"""
    cfg = ALL_CONFIGS[market_key]
    thr = threshold if threshold is not None else cfg.get("score_threshold", SCORE_THRESHOLD)

    path = CACHE_DIR / f"panel_{market_key}.parquet"
    if not path.exists():
        raise SystemExit(f"패널 없음 — 먼저 실행: python replay.py build --market {market_key}")

    panel = _attach_scores(pd.read_parquet(path), {**cfg, "score_threshold": thr})

    # 손절 미적용 변형도 같이 담는다 — 손절이 성과를 깎는지 패턴이 부진한지 화면에서 갈라 봐야 함
    results = {}
    for hold in HORIZONS:
        for top_k in GRID_TOPS:
            for key in EVAL_KEYS:
                results[f"{key}|{hold}|{top_k}"] = evaluate(panel, key, hold, top_k, thr)
                results[f"{key}|{hold}|{top_k}|nostop"] = evaluate(
                    panel, key, hold, top_k, thr, no_stop=True)

    return {
        "market":       market_key,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date_from":    str(panel["date"].min())[:10],
        "date_to":      str(panel["date"].max())[:10],
        "panel_rows":   int(len(panel)),
        "n_tickers":    int(panel["ticker"].nunique()),
        "n_dates":      int(panel["date"].nunique()),
        "threshold":    thr,
        "holds":        HORIZONS,
        "tops":         GRID_TOPS,
        "costs": {
            "fee_rate": cfg.get("fee_rate", 0.0),
            "tax_rate": cfg.get("tax_rate", 0.0),
            "slippage": cfg.get("slippage", 0.0),
        },
        "results": results,
    }


def verify(market_key: str, n: int = 15) -> int:
    """
    창 길이에 따라 값이 달라지는 지표가 섞여 들어가면 재현 결과가 실제 화면과 다른 걸 재게 된다.

    조회 '시작일'을 달리하는 방식은 검증이 되지 않는다 — calc_signals_from_df가 내부에서
    lookback_bars로 잘라내므로 두 프레임이 같은 300봉으로 수렴해 항상 통과한다.
    잘라내는 봉 수 자체를, 그것도 크게 벌려야 창 의존성이 드러난다(300봉 vs 전체 히스토리).
    """
    cfg = ALL_CONFIGS[market_key]
    universe = pd.DataFrame(get_universe(cfg)).head(n)

    start = _last_weekday(datetime.today() - timedelta(days=cfg["bt_days"]),
                          skip_weekends=cfg.get("skip_weekends", True))
    full = {**cfg, "lookback_bars": None}   # 자르지 않음 — 기준선 차이를 최대로

    checked = mismatched = 0
    for t in universe["ticker"]:
        try:
            hist = sanitize_ohlc(drop_partial_bar(fdr.DataReader(t, start), cfg))
        except Exception:
            continue
        # 자르는 창(lookback)과 전체 히스토리 사이에 충분한 차이가 있어야 창 의존성이 드러난다
        if hist.empty or len(hist) < cfg["lookback_bars"] + 200:
            continue
        s1 = calc_signals_from_df(hist, cfg=cfg)
        s2 = calc_signals_from_df(hist, cfg=full)
        if s1 is None or s2 is None:
            continue
        checked += 1
        diff = {k: (s1[k], s2[k]) for k in s1 if _differs(s1[k], s2[k])}
        if diff:
            mismatched += 1
            print(f"  ✗ {t} 불일치: {diff}")

    print(f"\n동일성 검증: {checked}종목 확인 / 불일치 {mismatched}종목")
    # 조회 실패나 히스토리 부족으로 하나도 못 봤는데 통과시키면, 검증 안 된 신호 경로로
    # 몇 시간짜리 적재가 진행된다 — '불일치 0'과 '확인 0'은 다르다
    floor = max(5, n // 2)
    if checked < floor:
        print(f"  → 검증 표본 부족 ({checked} < {floor}). 데이터 조회 실패 의심 — 통과시키지 않습니다.")
        return 1
    if mismatched:
        print("  → 창 길이에 의존하는 지표가 있습니다. 재현 결과를 신뢰할 수 없습니다.")
    else:
        print("  → 라이브와 재현이 동일한 신호를 냅니다.")
    return mismatched


def main():
    p = argparse.ArgumentParser(description="패턴 리스트 과거 재현")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="신호 패널 적재 (느림, 1회)")
    b.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    b.add_argument("--days", type=int, default=1100)
    b.add_argument("--interval", type=int, default=5, help="스캔 간격 (거래일)")
    b.add_argument("--sample", type=int, default=None, help="종목 표본 수 (시험용)")

    e = sub.add_parser("eval", help="조건별 집계 (빠름, 반복)")
    e.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    e.add_argument("--hold", type=int, default=20, choices=HORIZONS)
    e.add_argument("--top", type=int, default=30)
    e.add_argument("--pattern", default=None, help="단일 패턴만 (기본: 전체)")
    e.add_argument("--threshold", type=float, default=None)
    e.add_argument("--no-stop", action="store_true", help="손절 없이 만기까지 보유")
    e.add_argument("--json", default=None, help="결과를 JSON으로 저장")

    k = sub.add_parser("picks", help="특정 날짜 리스트의 종목별 수익률")
    k.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    k.add_argument("--pattern", required=True)
    k.add_argument("--hold", default="now",
                   help="'now'=안 팔고 현재까지(기본), 또는 5/20/60 거래일 보유")
    k.add_argument("--top", type=int, default=30)
    k.add_argument("--date", default=None, help="기준일 (미지정 시 최근 스캔일)")
    k.add_argument("--threshold", type=float, default=None)
    k.add_argument("--no-stop", action="store_true")

    v = sub.add_parser("verify", help="라이브/재현 신호 동일성 검증")
    v.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    v.add_argument("--n", type=int, default=15)

    pub = sub.add_parser("publish", help="조합 그리드를 계산해 Firebase에 업로드")
    pub.add_argument("--market", default="kr", choices=list(ALL_CONFIGS))
    pub.add_argument("--threshold", type=float, default=None)
    pub.add_argument("--dry-run", action="store_true", help="업로드 없이 JSON만 출력")

    a = p.parse_args()
    if a.cmd == "build":
        build(a.market, a.days, a.interval, a.sample)
    elif a.cmd == "picks":
        hold = None if str(a.hold) == "now" else int(a.hold)
        picks(a.market, a.pattern, hold, a.top, a.date, a.threshold, no_stop=a.no_stop)
    elif a.cmd == "verify":
        sys.exit(1 if verify(a.market, a.n) else 0)
    elif a.cmd == "publish":
        grid = build_grid(a.market, a.threshold)
        print(f"조합 {len(grid['results'])}개 계산 "
              f"({grid['date_from']} ~ {grid['date_to']}, {grid['n_tickers']}종목)")
        docs, index = build_picks_docs(a.market, top_k=max(GRID_TOPS), threshold=a.threshold)
        print(f"종목 내역 {len(docs)}일 준비")
        if a.dry_run:
            out = CACHE_DIR / f"grid_{a.market}.json"
            out.write_text(json.dumps(grid, ensure_ascii=False, indent=2))
            out2 = CACHE_DIR / f"picks_{a.market}.json"
            out2.write_text(json.dumps({"index": index, "docs": docs}, ensure_ascii=False, indent=2))
            print(f"dry-run -> {out}")
            print(f"dry-run -> {out2}")
        else:
            import firebase_upload
            firebase_upload.save_replay(a.market, grid)
            firebase_upload.save_replay_picks(a.market, docs, index)
    else:
        keys = [a.pattern] if a.pattern else EVAL_KEYS
        stats = report(a.market, a.hold, a.top, keys, a.threshold, no_stop=a.no_stop)
        if a.json:
            Path(a.json).write_text(json.dumps(stats, ensure_ascii=False, indent=2))
            print(f"\nJSON 저장 → {a.json}")


if __name__ == "__main__":
    main()
