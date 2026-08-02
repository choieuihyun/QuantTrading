import os
import sys
import screener
import firebase_upload
import dart_fetcher
import backtest
from market_config import ALL_CONFIGS

PATTERN_NAMES = {
    "p1":         "정배열 퍼지기 직전 + 매집",
    "p2":         "5일선 추세 + 거래량 터짐",
    "p3":         "눌림목",
    "canslim":    "O'Neil CAN SLIM",
    "vcp":        "Minervini VCP",
    "stage2":     "Weinstein Stage 2",
    "wyckoff":    "Wyckoff 매집",
    "darvas":     "Darvas Box 돌파",
    "common_trend": "★ 추세 공통 (유명 패턴)",
    "common_accum": "★ 매집 공통 (유명 패턴)",
    "common_all":   "☆ 내 패턴 공통",
}


def main():
    run_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print(f"Running screener [{run_type}]...")

    all_market_results = {}

    # ── 3개 시장 순차 실행 ─────────────────────────────────
    for market_key, cfg in ALL_CONFIGS.items():
        results = screener.run(cfg)

        # DART 펀더멘털 보강 (KR만)
        if market_key == "kr" and os.environ.get("DART_API_KEY"):
            all_tickers = set()
            for df in results.values():
                if hasattr(df, "empty") and not df.empty:
                    all_tickers.update(df["ticker"].tolist())

            if all_tickers:
                print(f"\nDART 펀더멘털 수집 중 ({len(all_tickers)}종목)...")
                dart_data = dart_fetcher.fetch_batch(list(all_tickers))
                for key, df in results.items():
                    if hasattr(df, "empty") and not df.empty:
                        results[key] = df.merge(dart_data, on="ticker", how="left")

        all_market_results[market_key] = results

        # 결과 출력
        print(f"\n{'='*40}")
        for key, df in results.items():
            name = PATTERN_NAMES.get(key, key)
            print(f"  [{name}] {len(df)}종목")
            if not df.empty:
                cols = ["ticker", "name", "score"]
                if "eps_yoy" in df.columns:
                    cols.append("eps_yoy")
                print("  " + df[cols].head(3).to_string())

    # ── 백테스트 (3개 시장 각각) ───────────────────────────
    # 스크리너 결과와 무관한 유니버스 표본을 스캔 — 선정된 종목만 되짚으면
    # 이미 오른 종목의 과거를 재는 셈이라 승률이 부풀려짐
    all_backtest = {}

    for market_key, cfg in ALL_CONFIGS.items():
        print(f"\n[{cfg['name']}] 백테스트 실행 중...")
        try:
            all_backtest[market_key] = backtest.run(cfg)
        except Exception as e:
            print(f"  백테스트 실패: {e}")
            all_backtest[market_key] = {}

    # ── Firebase 업로드 ────────────────────────────────────
    firebase_upload.upload(all_market_results, run_type=run_type, backtest=all_backtest)
    print("\nDone.")


if __name__ == "__main__":
    main()
