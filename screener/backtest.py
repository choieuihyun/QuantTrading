import pandas as pd
import FinanceDataReader as fdr
from concurrent.futures import ThreadPoolExecutor, as_completed
from screener import (
    calc_signals_from_df,
    _score_stage2, _score_canslim, _score_darvas,
    _score_wyckoff, _score_vcp,
    _score_p1, _score_p2, _score_p3,
    SCORE_THRESHOLD, _last_weekday,
)
from datetime import datetime, timedelta

HOLD_DAYS = [20, 60]
SCAN_INTERVAL = 5      # 매 5거래일(1주)마다 신호 체크
MIN_HIST = 120         # 신호 계산 최소 필요 데이터


def _is_trend_signal(s: dict) -> bool:
    hits = sum([
        _score_stage2(s)  >= SCORE_THRESHOLD,
        _score_canslim(s) >= SCORE_THRESHOLD,
        _score_darvas(s)  >= SCORE_THRESHOLD,
    ])
    return hits >= 2


def _is_accum_signal(s: dict) -> bool:
    return (
        _score_wyckoff(s) >= SCORE_THRESHOLD and
        _score_vcp(s)     >= SCORE_THRESHOLD
    )


def _is_custom_signal(s: dict) -> bool:
    hits = sum([
        _score_p1(s) >= SCORE_THRESHOLD,
        _score_p2(s) >= SCORE_THRESHOLD,
        _score_p3(s) >= SCORE_THRESHOLD,
    ])
    return hits >= 2


SIGNAL_FNS = {
    "common_trend": _is_trend_signal,
    "common_accum": _is_accum_signal,
    "common_all":   _is_custom_signal,
}


def _backtest_ticker(ticker: str, hist: pd.DataFrame, category: str) -> list[dict]:
    signal_fn = SIGNAL_FNS[category]
    trades = []
    total = len(hist)
    max_check = total - max(HOLD_DAYS) - 1

    for i in range(MIN_HIST, max_check, SCAN_INTERVAL):
        window = hist.iloc[:i + 1]
        signals = calc_signals_from_df(window, market_return=0.0)
        if signals is None:
            continue
        if not signal_fn(signals):
            continue

        entry_price = float(hist["Close"].iloc[i])
        entry_date  = str(hist.index[i])[:10]

        trade = {"ticker": ticker, "entry_date": entry_date, "entry_price": entry_price}
        for days in HOLD_DAYS:
            if i + days < total:
                exit_price = float(hist["Close"].iloc[i + days])
                trade[f"return_{days}d"] = round((exit_price - entry_price) / entry_price, 4)

        if any(f"return_{d}d" in trade for d in HOLD_DAYS):
            trades.append(trade)

    return trades


def _calc_stats(trades: list[dict], category: str) -> dict:
    if not trades:
        return {"category": category, "n_signals": 0}

    stats: dict = {"category": category, "n_signals": len(trades)}

    for days in HOLD_DAYS:
        key = f"return_{days}d"
        returns = [t[key] for t in trades if key in t]
        if not returns:
            continue

        wins    = [r for r in returns if r > 0]
        losses  = [r for r in returns if r <= 0]
        avg_win  = sum(wins)   / len(wins)   if wins   else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        stats[f"n_{days}d"]         = len(returns)
        stats[f"win_rate_{days}d"]  = round(len(wins) / len(returns), 4)
        stats[f"avg_return_{days}d"]= round(sum(returns) / len(returns), 4)
        stats[f"avg_win_{days}d"]   = round(avg_win, 4)
        stats[f"avg_loss_{days}d"]  = round(avg_loss, 4)
        stats[f"profit_factor_{days}d"] = round(
            abs(avg_win / avg_loss) if avg_loss != 0 else 0, 2
        )

    # 상위 3개 거래
    if trades and "return_20d" in trades[0]:
        best = sorted([t for t in trades if "return_20d" in t],
                      key=lambda x: x["return_20d"], reverse=True)[:3]
        stats["best_trades"] = best

    return stats


def run(results: dict, start_date: str) -> dict:
    """
    results: screener.run()의 반환값
    start_date: 데이터 시작일 (screener와 동일)
    """
    # 3개 카테고리에서 유니크 티커 수집
    tickers_by_cat: dict[str, list[str]] = {}
    for cat in ["common_trend", "common_accum", "common_all"]:
        df = results.get(cat)
        if df is not None and hasattr(df, "empty") and not df.empty:
            tickers_by_cat[cat] = df["ticker"].tolist()
        else:
            tickers_by_cat[cat] = []

    all_tickers = list({t for ts in tickers_by_cat.values() for t in ts})
    if not all_tickers:
        return {}

    print(f"\n백테스트 데이터 수집 중 ({len(all_tickers)}종목)...")

    # 히스토리 캐시 (ticker → DataFrame)
    hist_cache: dict[str, pd.DataFrame] = {}

    def fetch_hist(ticker: str):
        try:
            df = fdr.DataReader(ticker, start_date)
            return ticker, df if not df.empty else None
        except Exception:
            return ticker, None

    with ThreadPoolExecutor(max_workers=20) as ex:
        for ticker, df in ex.map(fetch_hist, all_tickers):
            if df is not None:
                hist_cache[ticker] = df

    print(f"히스토리 캐시 완료 ({len(hist_cache)}종목)")

    backtest_results = {}
    for cat, tickers in tickers_by_cat.items():
        if not tickers:
            backtest_results[cat] = {"category": cat, "n_signals": 0}
            continue

        all_trades: list[dict] = []
        for ticker in tickers:
            hist = hist_cache.get(ticker)
            if hist is None or len(hist) < MIN_HIST + max(HOLD_DAYS):
                continue
            trades = _backtest_ticker(ticker, hist, cat)
            all_trades.extend(trades)

        stats = _calc_stats(all_trades, cat)
        backtest_results[cat] = stats
        print(f"  [{cat}] 신호 {stats['n_signals']}개 "
              f"| 20일 승률 {stats.get('win_rate_20d', 0)*100:.0f}% "
              f"| 평균수익 {stats.get('avg_return_20d', 0)*100:.1f}%")

    return backtest_results
