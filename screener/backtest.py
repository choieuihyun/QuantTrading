import random

import numpy as np
import pandas as pd
import FinanceDataReader as fdr
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from screener import (
    calc_signals_from_df, drop_partial_bar, get_universe, score_pattern,
    TREND_PATTERN_KEYS, ACCUM_PATTERN_KEYS, CUSTOM_PATTERN_KEYS,
    SCORE_THRESHOLD, _last_weekday,
)

HOLD_DAYS     = [20, 60]
SCAN_INTERVAL = 10      # 20일 보유와 겹치는 중복 신호를 줄임
BT_SAMPLE     = 150     # 유니버스 표본 수 (전수 스캔은 Actions 시간 초과)
SAMPLE_SEED   = 42      # 실행마다 표본이 바뀌면 결과 비교가 불가능
MOMENTUM_BARS = 65      # 3개월 = 65거래일

# 보유기간별 손절선 — 스크리너가 화면에 표시하는 것과 동일한 기준
STOP_KEY = {20: "stop_swing", 60: "stop_lt"}


def _is_trend_signal(s: dict, cfg: dict) -> bool:
    t = cfg.get("score_threshold", SCORE_THRESHOLD)
    return sum(score_pattern(k, s, cfg) >= t for k in TREND_PATTERN_KEYS) >= 2


def _is_accum_signal(s: dict, cfg: dict) -> bool:
    t = cfg.get("score_threshold", SCORE_THRESHOLD)
    return all(score_pattern(k, s, cfg) >= t for k in ACCUM_PATTERN_KEYS)


def _is_custom_signal(s: dict, cfg: dict) -> bool:
    t = cfg.get("score_threshold", SCORE_THRESHOLD)
    return sum(score_pattern(k, s, cfg) >= t for k in CUSTOM_PATTERN_KEYS) >= 2


SIGNAL_FNS = {
    "common_trend": _is_trend_signal,
    "common_accum": _is_accum_signal,
    "common_all":   _is_custom_signal,
}


def _net_return(entry: float, exit_price: float, cfg: dict) -> float:
    """수수료·세금·슬리피지 반영 실현 수익률"""
    buy_cost  = cfg.get("fee_rate", 0.0) + cfg.get("slippage", 0.0)
    sell_cost = cfg.get("fee_rate", 0.0) + cfg.get("slippage", 0.0) + cfg.get("tax_rate", 0.0)
    eff_entry = entry * (1 + buy_cost)
    eff_exit  = exit_price * (1 - sell_cost)
    return (eff_exit - eff_entry) / eff_entry


def _resolve_exit(lows, opens, closes, i: int, days: int, stop: float) -> tuple[float, bool]:
    """손절 도달 시 조기 청산 — 갭하락이면 시가로 체결되므로 손절가보다 불리"""
    seg = lows[i + 1 : i + days + 1]
    hit = np.flatnonzero(seg <= stop)
    if hit.size:
        j = i + 1 + int(hit[0])
        return min(stop, float(opens[j])), True
    return float(closes[i + days]), False


def _backtest_ticker(ticker: str, hist: pd.DataFrame, bench: pd.Series, cfg: dict) -> dict:
    """한 종목의 전 구간을 1회 스캔하며 3개 카테고리를 동시에 평가"""
    min_hist = max(cfg.get("bars_per_year", 252), 150)
    total    = len(hist)
    max_scan = total - max(HOLD_DAYS) - 1
    if max_scan <= min_hist:
        return {cat: [] for cat in SIGNAL_FNS}

    lows   = hist["Low"].to_numpy(dtype=float)
    opens  = hist["Open"].to_numpy(dtype=float)
    closes = hist["Close"].to_numpy(dtype=float)

    bench_aligned = bench.reindex(hist.index).ffill().to_numpy(dtype=float)

    trades = {cat: [] for cat in SIGNAL_FNS}

    for i in range(min_hist, max_scan, SCAN_INTERVAL):
        # 신호 시점의 벤치마크 3개월 수익률 — rs를 라이브와 동일하게 계산
        b_now, b_ref = bench_aligned[i], bench_aligned[i - MOMENTUM_BARS]
        if not np.isfinite(b_now) or not np.isfinite(b_ref) or b_ref <= 0:
            continue
        market_return = round((b_now - b_ref) / b_ref, 4)

        window  = hist.iloc[: i + 1]
        signals = calc_signals_from_df(window, market_return=market_return, cfg=cfg)
        if signals is None:
            continue

        matched = [cat for cat, fn in SIGNAL_FNS.items() if fn(signals, cfg)]
        if not matched:
            continue

        entry_price = float(closes[i])
        entry_date  = str(hist.index[i])[:10]

        trade = {"ticker": ticker, "entry_date": entry_date, "entry_price": entry_price}
        for days in HOLD_DAYS:
            if i + days >= total:
                continue
            stop = float(signals[STOP_KEY[days]])
            exit_price, stopped = _resolve_exit(lows, opens, closes, i, days, stop)
            trade[f"return_{days}d"]   = round(_net_return(entry_price, exit_price, cfg), 4)
            trade[f"stopped_{days}d"]  = stopped

        if any(f"return_{d}d" in trade for d in HOLD_DAYS):
            for cat in matched:
                trades[cat].append(dict(trade))

    return trades


def _calc_stats(trades: list[dict], category: str) -> dict:
    if not trades:
        return {"category": category, "n_signals": 0}

    stats: dict = {"category": category, "n_signals": len(trades)}
    stats["n_tickers"] = len({t["ticker"] for t in trades})

    for days in HOLD_DAYS:
        key = f"return_{days}d"
        returns = [t[key] for t in trades if key in t]
        if not returns:
            continue

        wins   = [r for r in returns if r > 0]
        losses = [r for r in returns if r <= 0]
        avg_win  = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        gross_win  = sum(wins)
        gross_loss = abs(sum(losses))

        stats[f"n_{days}d"]          = len(returns)
        stats[f"win_rate_{days}d"]   = round(len(wins) / len(returns), 4)
        stats[f"avg_return_{days}d"] = round(sum(returns) / len(returns), 4)
        stats[f"median_return_{days}d"] = round(float(np.median(returns)), 4)
        stats[f"avg_win_{days}d"]    = round(avg_win, 4)
        stats[f"avg_loss_{days}d"]   = round(avg_loss, 4)
        # 총이익/총손실 — 승률이 반영된 실제 기대값 지표
        # 손실 0건이면 값이 정의되지 않음 → None (0.0으로 두면 최악 성과로 오독됨)
        stats[f"profit_factor_{days}d"] = round(gross_win / gross_loss, 2) if gross_loss else None
        # 평균이익/평균손실 — 건당 손익비
        stats[f"payoff_ratio_{days}d"]  = round(abs(avg_win / avg_loss), 2) if avg_loss else None
        stopped = [t.get(f"stopped_{days}d") for t in trades if key in t]
        stats[f"stop_hit_rate_{days}d"] = round(sum(bool(x) for x in stopped) / len(stopped), 4)

    if "return_20d" in trades[0]:
        best = sorted([t for t in trades if "return_20d" in t],
                      key=lambda x: x["return_20d"], reverse=True)[:3]
        stats["best_trades"] = [
            {k: v for k, v in t.items() if k in ("ticker", "entry_date", "return_20d")}
            for t in best
        ]

    return stats


def run(cfg: dict, sample_size: int = BT_SAMPLE) -> dict:
    """
    유니버스 전체에서 표본을 뽑아 과거 시점 스캔 — 오늘 선정된 종목만 보면
    '이미 오른 종목의 과거'를 측정하게 되어 승률이 구조적으로 부풀려짐.
    """
    today      = datetime.today()
    skip_wknd  = cfg.get("skip_weekends", True)
    start_date = _last_weekday(today - timedelta(days=cfg.get("bt_days", 1100)), skip_weekends=skip_wknd)

    universe = get_universe(cfg)
    if not universe:
        return {}

    tickers = [r["ticker"] for r in universe]
    if len(tickers) > sample_size:
        tickers = random.Random(SAMPLE_SEED).sample(tickers, sample_size)
        print(f"백테스트 표본: 유니버스 {len(universe)}종목 중 {len(tickers)}종목 (seed={SAMPLE_SEED})")
    else:
        print(f"백테스트 표본: 유니버스 전체 {len(tickers)}종목")

    bench_raw = fdr.DataReader(cfg["benchmark"], start_date)
    if bench_raw.empty:
        raise RuntimeError(f"벤치마크 {cfg['benchmark']} 데이터 없음 — 백테스트 중단")
    bench = bench_raw["Close"]

    def fetch_hist(ticker: str):
        try:
            df = fdr.DataReader(ticker, start_date)
            df = drop_partial_bar(df, cfg)
            return ticker, df if not df.empty else None
        except Exception:
            return ticker, None

    hist_cache: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=20) as ex:
        for ticker, df in ex.map(fetch_hist, tickers):
            if df is not None:
                hist_cache[ticker] = df

    min_bars = max(cfg.get("bars_per_year", 252), 150) + max(HOLD_DAYS) + 1
    usable = {t: h for t, h in hist_cache.items() if len(h) >= min_bars}
    print(f"히스토리 확보 {len(hist_cache)}종목 / 스캔 가능 {len(usable)}종목 (최소 {min_bars}봉)")

    all_trades: dict[str, list[dict]] = {cat: [] for cat in SIGNAL_FNS}
    for ticker, hist in usable.items():
        result = _backtest_ticker(ticker, hist, bench, cfg)
        for cat, trades in result.items():
            all_trades[cat].extend(trades)

    backtest_results = {}
    for cat, trades in all_trades.items():
        stats = _calc_stats(trades, cat)
        stats["universe_size"] = len(universe)
        stats["sample_size"]   = len(usable)
        stats["scan_interval"] = SCAN_INTERVAL
        stats["costs"] = {
            "fee_rate": cfg.get("fee_rate", 0.0),
            "tax_rate": cfg.get("tax_rate", 0.0),
            "slippage": cfg.get("slippage", 0.0),
        }
        backtest_results[cat] = stats
        pf = stats.get("profit_factor_20d")
        print(f"  [{cat}] 신호 {stats['n_signals']}개 "
              f"| 20일 승률 {stats.get('win_rate_20d', 0)*100:.0f}% "
              f"| 평균수익 {stats.get('avg_return_20d', 0)*100:.1f}% "
              f"| PF {'∞' if pf is None else pf}")

    return backtest_results
