import os
import sys
import screener
import firebase_upload
import dart_fetcher

PATTERN_NAMES = {
    "p1":         "정배열 퍼지기 직전 + 매집",
    "p2":         "5일선 추세 + 거래량 터짐",
    "p3":         "눌림목",
    "canslim":    "O'Neil CAN SLIM",
    "vcp":        "Minervini VCP",
    "stage2":     "Weinstein Stage 2",
    "wyckoff":    "Wyckoff 매집",
    "darvas":     "Darvas Box 돌파",
    "common_trend": "★ 추세 공통 (Stage2+CAN SLIM+Darvas)",
    "common_accum": "★ 매집 공통 (Wyckoff+VCP)",
    "common_all":   "☆ 내 패턴 공통 (P1+P2+P3)",
}


def main():
    run_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print(f"Running screener [{run_type}]...\n")

    results = screener.run()

    # ── DART 펀더멘털 보강 ─────────────────────────────────
    all_tickers = set()
    for df in results.values():
        if hasattr(df, "empty") and not df.empty:
            all_tickers.update(df["ticker"].tolist())

    if all_tickers and os.environ.get("DART_API_KEY"):
        print(f"\nDART 펀더멘털 수집 중 ({len(all_tickers)}종목)...")
        dart_data = dart_fetcher.fetch_batch(list(all_tickers))
        for key, df in results.items():
            if hasattr(df, "empty") and not df.empty:
                results[key] = df.merge(dart_data, on="ticker", how="left")

    # ── 출력 ───────────────────────────────────────────────
    print("\n" + "=" * 50)
    for key, df in results.items():
        name = PATTERN_NAMES.get(key, key)
        print(f"\n[{name}] {len(df)}종목")
        if not df.empty:
            cols = ["ticker", "name", "score"]
            if "eps_yoy" in df.columns:
                cols.append("eps_yoy")
            if "canslim_c" in df.columns:
                cols.append("canslim_c")
            print(df[cols].head(5).to_string())

    firebase_upload.upload(results, run_type=run_type)
    print("\nDone.")


if __name__ == "__main__":
    main()
