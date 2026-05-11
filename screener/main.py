import sys
import screener
import firebase_upload


def main():
    run_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    print(f"Running screener [{run_type}]...")

    df = screener.run()
    print(f"Screened {len(df)} stocks")
    print(df[["ticker", "name", "score"]].head(10).to_string())

    firebase_upload.upload(df, run_type=run_type)
    print("Done.")


if __name__ == "__main__":
    main()
