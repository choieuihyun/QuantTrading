import os
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore


def _init_app():
    if not firebase_admin._apps:
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.environ["FIREBASE_PROJECT_ID"],
            "private_key": os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
            "token_uri": "https://oauth2.googleapis.com/token",
        })
        firebase_admin.initialize_app(cred)


def _to_native(val):
    if hasattr(val, "item"):
        return val.item()
    if isinstance(val, bool):
        return bool(val)
    return val


def _serialize_df(df) -> list:
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            r[k] = _to_native(v)
    return records


def upload(all_market_results: dict, run_type: str = "auto", backtest: dict = None):
    """
    all_market_results: { "kr": {p1: df, ...}, "us": {...}, "crypto": {...} }
    backtest: { "kr": {common_trend: stats, ...}, "us": {...}, "crypto": {...} }
    """
    _init_app()
    db = firestore.client()

    market_date = datetime.today().strftime("%Y-%m-%d")
    doc_id = f"{market_date}_{run_type}"

    data = {
        "run_at":      datetime.now(timezone.utc),
        "market_date": market_date,
        "run_type":    run_type,
    }

    # 시장별 패턴 데이터 (kr_p1, us_common_trend, crypto_wyckoff 등)
    for market_key, results in all_market_results.items():
        for pattern_key, df in results.items():
            key = f"{market_key}_{pattern_key}"
            data[key] = _serialize_df(df)
            data[f"{key}_count"] = len(df)

    # 백테스트 데이터
    if backtest:
        data["backtest"] = backtest

    db.collection("screener_results").document(doc_id).set(data)
    print(f"\nUploaded → screener_results/{doc_id}")
    for mk, results in all_market_results.items():
        counts = {k: len(v) for k, v in results.items() if "common" in k}
        print(f"  [{mk}] {counts}")
