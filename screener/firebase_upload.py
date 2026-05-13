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


def upload(results: dict, run_type: str = "auto", backtest: dict = None):
    _init_app()
    db = firestore.client()

    market_date = datetime.today().strftime("%Y-%m-%d")
    doc_id = f"{market_date}_{run_type}"

    data = {
        "run_at":     datetime.now(timezone.utc),
        "market_date": market_date,
        "run_type":   run_type,
    }

    for key, df in results.items():
        records = df.to_dict(orient="records")
        for r in records:
            for k, v in r.items():
                r[k] = _to_native(v)
        data[key] = records
        data[f"{key}_count"] = len(records)

    if backtest:
        data["backtest"] = backtest

    db.collection("screener_results").document(doc_id).set(data)
    print(f"Uploaded → screener_results/{doc_id}")
