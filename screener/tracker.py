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


# 진입가를 이 비율 넘게 벗어나면 액면분할·무상증자 등 자본 조정이 있었다고 본다
ADJUST_TOL = 0.02


def build(db, price_maps: dict, markets: list[str], close_maps: dict = None) -> dict:
    """
    price_maps: { "kr": {ticker: 현재가}, ... } — 이번 실행에서 받은 전 종목 시세
    close_maps: { "kr": {ticker: {날짜: 종가}} } — 같은 실행에서 받은 종가 이력

    수익률은 저장된 진입가가 아니라 close_maps에서 다시 읽는다.
    저장값을 쓰면 그 사이 액면분할·무상증자가 있었을 때 조정 전 가격과 조정 후 가격을
    비교하게 된다. 실측: 티앤엘이 -47.8%로 찍혔는데 실제로는 +3.1%였고,
    9,606건 중 244건(77종목)이 이 오차를 안고 있었다.
    """
    cutoff = (datetime.today() - timedelta(days=TRACK_DAYS)).strftime("%Y-%m-%d")

    # 과거 스크리닝 결과를 읽어온다 (문서 하나에 3개 시장이 함께 들어 있음).
    # backtest 블록이 문서 용량의 대부분이라 필요한 필드만 골라 받는다.
    fields = (["market_date"] + [f"{m}_bar_date" for m in markets]
              + [f"{m}_{k}" for m in markets for k in PATTERN_KEYS])
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

    print(f"성적표: 과거 기록 {len(history)}건")

    out = {}
    for market in markets:
        prices = price_maps.get(market) or {}
        if not prices:
            continue
        closes = (close_maps or {}).get(market) or {}

        # 진입일은 시계가 아니라 데이터의 봉 날짜로 잡는다. 08:30 KST 실행이 UTC로는
        # 전날 23:30이라 market_date가 실제 시세 날짜와 어긋난다(월요일 아침은 이틀).
        # 라벨이 틀리면 그 날짜로 종가를 찾는 아래 조회도 같이 틀어진다.
        # bar_date는 이 수정 이후 실행부터 들어가므로 없으면 market_date로 되돌아간다.
        by_date = {}
        for _, d in history:
            by_date[d.get(f"{market}_bar_date") or d["market_date"]] = d
        dates = sorted(by_date)[-KEEP_DOCS:]

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
                    stored = r.get("price")
                    now    = prices.get(ticker)
                    # 오늘 받은 시계열에서 진입일 종가를 다시 읽는다 — 자본 조정 대응
                    entry  = (closes.get(ticker) or {}).get(date)
                    adjusted = bool(entry and stored
                                    and abs(stored / entry - 1) > ADJUST_TOL)
                    if entry is None:
                        entry = stored          # 이력에 없으면 저장값으로 (정확도 낮음)
                    ret = _pct(entry, now) if now is not None else None
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
                        # 자본 조정이 있었으면 score·rsi·pos_52w는 조정 전 기준이라 신뢰할 수 없다
                        "adjusted":     adjusted,
                        "stored_entry": stored if adjusted else None,
                    })
                    if ret is not None:
                        rets.append(ret)

                if len(picks) < MIN_PICKS:
                    continue

                patterns[key] = {
                    "picks": picks,
                    "adjusted": sum(1 for p in picks if p["adjusted"]),
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
