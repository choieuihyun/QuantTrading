import json
import math
import os
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore


# 로컬 실행용 서비스 계정 키. private key는 여러 줄이라 .env에 손으로 붙여넣으면
# 줄바꿈이 깨지기 쉽다 — Firebase 콘솔에서 받은 JSON을 그대로 두는 편이 안전하다.
# .gitignore에 등록돼 있다.
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "serviceAccount.json")


def _init_app():
    if firebase_admin._apps:
        return
    if os.environ.get("FIREBASE_PROJECT_ID"):       # Actions 경로
        cred = credentials.Certificate({
            "type": "service_account",
            "project_id": os.environ["FIREBASE_PROJECT_ID"],
            "private_key": os.environ["FIREBASE_PRIVATE_KEY"].replace("\\n", "\n"),
            "client_email": os.environ["FIREBASE_CLIENT_EMAIL"],
            "token_uri": "https://oauth2.googleapis.com/token",
        })
    elif os.path.exists(_KEY_FILE):                 # 로컬 경로
        cred = credentials.Certificate(_KEY_FILE)
        print(f"Firebase 인증: {os.path.basename(_KEY_FILE)}")
    else:
        raise SystemExit(
            "Firebase 자격증명이 없습니다.\n"
            "  Firebase 콘솔 → 프로젝트 설정 → 서비스 계정 → '새 비공개 키 생성'\n"
            f"  받은 JSON을 {_KEY_FILE} 로 저장하세요 (gitignore 처리됨)")
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


# Firestore 문서 한도는 용량(1MB)만이 아니다. 모든 필드가 자동 색인되고
# 색인 항목이 문서당 40,000개를 넘으면 쓰기가 거부된다
# (실측: 2,786종목 × 10필드 × 2 ≈ 55,700개 → INDEX_ENTRIES_COUNT_LIMIT_EXCEEDED).
# 종목별 데이터를 JSON 문자열 한 덩어리로 저장하면 색인 항목이 1개가 된다.
# 어차피 화면은 문서를 통째로 받아 종목 하나를 꺼내 쓰므로 손해가 없다.
MAX_FIELD_BYTES = 1_000_000


def _packed(obj: dict, label: str) -> str:
    s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    n = len(s.encode())
    if n > MAX_FIELD_BYTES:
        raise ValueError(f"{label} 직렬화 {n/1024:.0f}KB — 문자열 필드 한도(약 1MB) 초과")
    print(f"  {label}: {len(obj)}종목 → {n/1024:.0f}KB (색인 항목 1개)")
    return s


def _reject_nested_arrays(o, path=""):
    """Firestore는 배열 요소로 배열을 허용하지 않는다. 위반하면 문서 전체가 거부되는데
    호출부가 예외를 삼키면 화면에는 '데이터 없음'만 남아 원인을 못 찾는다."""
    if isinstance(o, dict):
        for k, v in o.items():
            _reject_nested_arrays(v, f"{path}.{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if isinstance(v, list):
                raise ValueError(f"중첩 배열 {path}[{i}] — Firestore가 거부합니다")
            _reject_nested_arrays(v, f"{path}[{i}]")


def save_signals(market: str, shards: dict, labels: dict, bar_date: str, threshold: float):
    """
    종목별 패턴 판정 — "이 종목이 왜 목록에 없지?"에 답하는 데이터.

    전 종목 × 11패턴 × 조건별 실측값은 한 문서(1MB)를 넘어 샤드로 쪼갠다.
    화면은 검색한 종목이 속한 샤드 하나만 읽으면 된다.
    """
    if not shards:
        return
    _init_app()
    db = firestore.client()

    # 샤드 하나가 150KB대라 한 배치로 묶으면 커밋 요청이 커진다. 개별로 쓴다.
    for i, rows in shards.items():
        db.collection("signals").document(f"{market}_{i}").set(
            {"bar_date": bar_date, "tickers_json": _packed(rows, f"signals[{i}]")})
    db.collection("signals").document(f"{market}_index").set({
        "bar_date": bar_date,
        "run_at": datetime.now(timezone.utc),
        "threshold": threshold,
        "shards": len(shards),
        "labels": labels,
        "count": sum(len(r) for r in shards.values()),
    })
    print(f"Uploaded → signals/{market}_* ({sum(len(r) for r in shards.values())}종목 / {len(shards)}샤드)")


def save_flows(market: str, tickers: dict, legend: dict, dist: dict, bar_date: str):
    """
    KRX 수급·공매도·밸류에이션. 로컬 실행(enrich_local.py)에서만 채워진다 —
    KRX가 데이터센터 IP를 막아 Actions에서는 받을 수 없다.

    Actions가 하루 2번 덮어쓰는 prices/{market}과 분리해 둔다. 같은 문서에 넣으면
    다음 자동 실행이 수급 데이터를 지운다.
    """
    if not tickers:
        return
    _init_app()
    db = firestore.client()
    db.collection("flows").document(market).set({
        "bar_date": bar_date,
        "run_at": datetime.now(timezone.utc),
        "count": len(tickers),
        "legend": legend,          # 저장 키가 짧아 뜻을 문서 안에 같이 둔다
        # 0~100 분위 경계값. 종목마다 백분위를 저장하는 대신 분포만 한 번 담는다.
        "dist": dist,
        "tickers_json": _packed(tickers, "flows"),
    })
    print(f"Uploaded → flows/{market} ({len(tickers)}종목, 기준 {bar_date})")


def save_disclosures(market: str, tickers: dict, bar_date: str):
    """
    종목별 공시 — 상세 화면에서 읽는다. 패턴 목록에 오른 종목만 수집한다.

    DART는 KRX와 무관한 서버라 Actions에서도 접속된다. 자본 조정 공시(무상증자·분할)는
    보유 수익률 계산을 통째로 틀어지게 하므로 화면에서 눈에 띄게 표시해야 한다.
    """
    if not tickers:
        return
    _init_app()
    db = firestore.client()
    db.collection("disclosures").document(market).set({
        "bar_date": bar_date,
        "run_at": datetime.now(timezone.utc),
        "count": len(tickers),
        "tickers_json": _packed(tickers, "disclosures"),
    })
    print(f"Uploaded → disclosures/{market} ({len(tickers)}종목)")


def attach_backtest(run_type: str, backtest: dict):
    """백테스트는 스크리닝 업로드 후에 끝나므로 같은 문서에 나중에 덧붙인다"""
    _init_app()
    db = firestore.client()
    doc_id = f"{datetime.today().strftime('%Y-%m-%d')}_{run_type}"
    db.collection("screener_results").document(doc_id).set({"backtest": backtest}, merge=True)
    print(f"Attached backtest → screener_results/{doc_id}")


def upload(all_market_results: dict, run_type: str = "auto", backtest: dict = None,
           bar_dates: dict = None):
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

    # 시장별 실제 봉 날짜. market_date는 UTC 시계라 08:30 KST 실행에서 하루 어긋난다.
    # 성적표가 이 날짜로 종가를 되짚으므로 라벨이 정확해야 한다.
    for market_key, md in (bar_dates or {}).items():
        if not md:
            continue
        data[f"{market_key}_bar_date"] = md.get("bar_date")
        # 시장 폭 — 자체 패턴은 장이 무너져도 계속 신호를 내므로 화면에서 함께 보여야 한다
        data[f"{market_key}_breadth"] = md.get("breadth")
        data[f"{market_key}_market_uptrend"] = md.get("market_uptrend")

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
