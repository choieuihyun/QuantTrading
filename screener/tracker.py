"""
실전 성적표 — "N일 전 이 패턴에 떴던 종목, 지금 몇 %?"

replay.py가 과거를 재구성하는 것과 달리, 여기서는 **실제로 화면에 떴던 기록**을 쓴다.
screener_results에 매일 저장된 패턴별 종목 목록을 읽어, 그때 표시됐던 가격과
오늘 가격을 비교한다. 재구성이 아니라 사실이라 생존편향·룩어헤드가 없다.

일일 스크리너가 이미 전 종목 시세를 받아둔 상태라 추가 조회 없이 계산된다.
"""

from datetime import datetime, timedelta

TRACK_DAYS   = 75    # 과거 문서를 며칠치까지 훑을지 (약 2.5개월)
KEEP_DOCS    = 40    # 화면에서 고를 수 있는 진입일 수
MIN_PICKS    = 1     # 이보다 적으면 성적표에 담지 않음

PATTERN_KEYS = ["p1", "p2", "p3", "canslim", "vcp", "stage2", "wyckoff", "darvas",
                "common_trend", "common_accum", "common_all"]


def _pct(entry: float, now: float) -> float | None:
    if not entry or entry <= 0 or not now or now <= 0:
        return None
    return round((now - entry) / entry, 4)


def build(db, price_maps: dict, markets: list[str]) -> dict:
    """
    price_maps: { "kr": {ticker: 현재가}, ... } — 이번 실행에서 받은 전 종목 시세
    반환: { market: {"index": {...}, "docs": [{...}, ...]} }
    """
    cutoff = (datetime.today() - timedelta(days=TRACK_DAYS)).strftime("%Y-%m-%d")

    # 과거 스크리닝 결과를 읽어온다 (문서 하나에 3개 시장이 함께 들어 있음).
    # backtest 블록이 문서 용량의 대부분이라 필요한 필드만 골라 받는다.
    fields = ["market_date"] + [f"{m}_{k}" for m in markets for k in PATTERN_KEYS]
    snaps = (db.collection("screener_results")
               .where("market_date", ">=", cutoff)
               .order_by("market_date")
               .select(fields)
               .stream())

    history = []
    for snap in snaps:
        d = snap.to_dict() or {}
        if d.get("market_date"):
            history.append((snap.id, d))

    if not history:
        print("성적표: 과거 스크리닝 기록이 없습니다")
        return {}

    # 같은 날 두 번(08:30/18:00) 실행되므로 날짜당 마지막 문서만 쓴다
    by_date = {}
    for doc_id, d in history:
        by_date[d["market_date"]] = d
    dates = sorted(by_date)[-KEEP_DOCS:]

    print(f"성적표: 과거 기록 {len(history)}건 → 진입일 {len(dates)}일 사용")

    out = {}
    for market in markets:
        prices = price_maps.get(market) or {}
        if not prices:
            continue

        docs = []
        for date in dates:
            src = by_date[date]
            patterns = {}

            for key in PATTERN_KEYS:
                rows = src.get(f"{market}_{key}")
                if not rows:
                    continue

                picks, rets = [], []
                for r in rows:
                    ticker = str(r.get("ticker", ""))
                    entry  = r.get("price")
                    now    = prices.get(ticker)
                    ret    = _pct(entry, now) if now is not None else None
                    # now가 없으면 상장폐지·거래정지로 오늘 유니버스에서 빠진 것 — 버리지 않고 표시
                    picks.append({
                        "ticker": ticker,
                        "name":   r.get("name", ""),
                        "score":  r.get("score"),
                        "entry":  entry,
                        "now":    now,
                        "ret":    ret,
                        "stop_swing": r.get("stop_swing"),
                        "rsi":    r.get("rsi"),
                        "pos_52w": r.get("pos_52w"),
                        "gone":   now is None,
                    })
                    if ret is not None:
                        rets.append(ret)

                if len(picks) < MIN_PICKS:
                    continue

                patterns[key] = {
                    "picks": picks,
                    "n":     len(rets),
                    "gone":  sum(1 for p in picks if p["gone"]),
                    "avg":   round(sum(rets) / len(rets), 4) if rets else None,
                    "median": round(sorted(rets)[len(rets) // 2], 4) if rets else None,
                    "wins":  sum(1 for r in rets if r > 0),
                    "best":  round(max(rets), 4) if rets else None,
                    "worst": round(min(rets), 4) if rets else None,
                }

            if patterns:
                docs.append({"market": market, "date": date, "patterns": patterns})

        if not docs:
            continue

        today = datetime.today().strftime("%Y-%m-%d")
        out[market] = {
            "index": {
                "market":       market,
                "updated_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
                "price_date":   today,
                "patterns":     PATTERN_KEYS,
                "dates": [
                    {"date": d["date"],
                     "days_ago": (datetime.strptime(today, "%Y-%m-%d")
                                  - datetime.strptime(d["date"], "%Y-%m-%d")).days}
                    for d in docs
                ],
            },
            "docs": docs,
        }
        print(f"  [{market}] 진입일 {len(docs)}일 × 패턴별 성적표")

    return out
