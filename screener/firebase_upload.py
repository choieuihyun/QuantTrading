import math
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
        val = val.item()
    if isinstance(val, bool):
        return bool(val)
    # pandas가 결측을 NaN으로 바꿔 놓는데, 그대로 올리면 프론트의 null 검사를 통과해
    # 화면에 "NaN%"으로 찍힌다. 여기서 None으로 정규화한다.
    if isinstance(val, float) and math.isnan(val):
        return None
    return val


def _serialize_df(df) -> list:
    records = df.to_dict(orient="records")
    for r in records:
        for k, v in r.items():
            r[k] = _to_native(v)
    return records


def save_fundamentals(histories: dict):
    """
    분기 재무 히스토리를 종목별 문서로 저장 (screener_results 문서 1MB 한도 회피).
    histories: { ticker: {corp_code, quarters: {"2024Q3": {...}, ...}} }
    """
    if not histories:
        return
    _init_app()
    db = firestore.client()

    batch = db.batch()
    n = 0
    for ticker, payload in histories.items():
        ref = db.collection("fundamentals").document(str(ticker))
        batch.set(ref, {
            "corp_code":  payload["corp_code"],
            "updated_at": datetime.now(timezone.utc),
            "quarters":   payload["quarters"],
        })
        n += 1
        if n % 400 == 0:  # Firestore 배치 한도 500
            batch.commit()
            batch = db.batch()
    batch.commit()
    print(f"fundamentals 저장: {n}종목")


def save_replay(market_key: str, grid: dict):
    """
    재현 백테스트 결과를 시장별 문서로 저장. 보유일·상위N 조합을 미리 계산해 두고
    대시보드는 조회만 하도록 만든다 (조합마다 재계산하면 화면에서 못 씀).
    """
    _init_app()
    db = firestore.client()
    db.collection("replay_results").document(market_key).set(grid)
    print(f"Uploaded → replay_results/{market_key} "
          f"(조합 {len(grid.get('results', {}))}개, {grid.get('date_from')} ~ {grid.get('date_to')})")


def save_replay_picks(market_key: str, docs: list, index: dict):
    """
    날짜별 종목 내역을 문서로 쪼개 저장. 전 기간을 한 문서에 담으면 1MB를 넘는다.
    화면은 사용자가 고른 날짜 하나만 읽으면 된다.
    """
    _init_app()
    db = firestore.client()

    batch, n = db.batch(), 0
    for doc in docs:
        ref = db.collection("replay_picks").document(f"{market_key}_{doc['date']}")
        batch.set(ref, doc)
        n += 1
        if n % 400 == 0:  # Firestore 배치 한도 500
            batch.commit()
            batch = db.batch()
    batch.set(db.collection("replay_picks").document(f"{market_key}_index"), index)
    batch.commit()
    print(f"Uploaded → replay_picks/{market_key}_* ({n}일 + index)")


def get_db():
    _init_app()
    return firestore.client()


def save_scorecard(scorecards: dict):
    """
    실전 성적표 — 진입일별 문서. 하루 2회 갱신되므로 현재가가 항상 최신이다.
    전 기간을 한 문서에 담으면 1MB를 넘어 날짜로 쪼갠다.
    """
    if not scorecards:
        return
    _init_app()
    db = firestore.client()

    batch, n = db.batch(), 0
    for market, payload in scorecards.items():
        for doc in payload["docs"]:
            ref = db.collection("scorecard").document(f"{market}_{doc['date']}")
            batch.set(ref, doc)
            n += 1
            if n % 400 == 0:  # Firestore 배치 한도 500
                batch.commit()
                batch = db.batch()
        batch.set(db.collection("scorecard").document(f"{market}_index"), payload["index"])
    batch.commit()
    print(f"Uploaded → scorecard/* ({n}개 문서)")


def save_prices(price_maps: dict, names: dict = None, meta: dict = None):
    """
    유니버스 전 종목 시세 — 가상 매매 평가용.

    패턴 목록에는 20종목만 담기므로, 산 종목이 다음날 목록에서 빠지면 현재가를 알 수 없다.
    스크리너가 이미 받아둔 전 종목 시세를 그대로 올려 그 구멍을 막는다.

    기준일은 시계가 아니라 데이터의 마지막 봉 날짜(bar_date)를 쓴다. 08:30 KST 실행이
    UTC로는 전날 23:30이라 datetime.today()는 실제 시세 날짜와 어긋난다(월요일 아침은 이틀).
    묵은 시세가 '현재가'로 조용히 표시되는 게 최악이라 화면에 이 날짜를 같이 보여준다.
    """
    if not price_maps:
        return
    _init_app()
    db = firestore.client()

    fallback = datetime.today().strftime("%Y-%m-%d")
    for market, prices in price_maps.items():
        if not prices:
            continue
        db.collection("prices").document(market).set({
            "market_date": ((meta or {}).get(market) or {}).get("bar_date") or fallback,
            "run_at": datetime.now(timezone.utc),
            "count": len(prices),
            "prices": {str(t): float(p) for t, p in prices.items()},
            "names": (names or {}).get(market, {}),
        })
        print(f"Uploaded → prices/{market} ({len(prices)}종목)")


def attach_backtest(run_type: str, backtest: dict):
    """백테스트는 스크리닝 업로드 후에 끝나므로 같은 문서에 나중에 덧붙인다"""
    _init_app()
    db = firestore.client()
    doc_id = f"{datetime.today().strftime('%Y-%m-%d')}_{run_type}"
    db.collection("screener_results").document(doc_id).set({"backtest": backtest}, merge=True)
    print(f"Attached backtest → screener_results/{doc_id}")


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
