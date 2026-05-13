import sys
import screener
import firebase_upload

PATTERN_NAMES = {
    "p1": "정배열 퍼지기 직전 + 매집",
    "p2": "5일선 추세 + 거래량 터짐",
    "p3": "눌림목",
}


def main():
    run_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print(f"Running screener [{run_type}]...")

    results = screener.run()

    for key, df in results.items():
        print(f"\n[{PATTERN_NAMES[key]}] {len(df)}종목")
        if not df.empty:
            print(df[["ticker", "name", "score"]].head(5).to_string())

    firebase_upload.upload(results, run_type=run_type)
    print("\nDone.")


if __name__ == "__main__":
    main()
