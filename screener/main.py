import os
import sys
import screener
import firebase_upload
import dart_fetcher
import backtest
import tracker
import investor_flow
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


CANSLIM_C_POINTS = 15   # 현분기 EPS +25% 충족 시 가산


def _apply_canslim_c(key: str, df):
    """
    CAN SLIM의 C(현분기 EPS +25%)를 점수에 반영.

    DART는 유니버스 전체가 아니라 '선정된 종목'만 조회하므로 선정 단계에서는 C를 쓸 수 없다.
    기술적 조건(N/S/L/M)으로 후보를 고른 뒤 여기서 C를 얹는 2단계 구조다.
    가산만 하고 감점하지 않으므로 후보 자체가 줄어들지는 않는다.
    """
    if key != "canslim" or "canslim_c" not in df.columns or "score" not in df.columns:
        return df
    bonus = df["canslim_c"].fillna(False).astype(bool) * CANSLIM_C_POINTS
    df = df.copy()
    df["score"] = (df["score"] + bonus).clip(upper=100)
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def main():
    run_type = sys.argv[1] if len(sys.argv) > 1 else "auto"
    # 두 번째 인자로 시장을 지정하면 그 시장만 실행 (예: python main.py auto kr)
    only = sys.argv[2] if len(sys.argv) > 2 else None
    configs = {only: ALL_CONFIGS[only]} if only in ALL_CONFIGS else ALL_CONFIGS
    print(f"Running screener [{run_type}] — 시장: {', '.join(configs)}")

    all_market_results = {}
    all_prices = {}
    all_names = {}
    all_meta = {}

    for market_key, cfg in configs.items():
        results, prices, names, meta = screener.run(cfg)
        all_prices[market_key] = prices
        all_names[market_key] = names
        all_meta[market_key] = meta

        # DART 펀더멘털 보강 (KR만)
        if market_key == "kr" and os.environ.get("DART_API_KEY"):
            all_tickers = set()
            for df in results.values():
                if hasattr(df, "empty") and not df.empty:
                    all_tickers.update(df["ticker"].tolist())

            if all_tickers:
                print(f"\nDART 펀더멘털 수집 중 ({len(all_tickers)}종목)...")
                dart_data, histories = dart_fetcher.fetch_batch(list(all_tickers))
                for key, df in results.items():
                    if hasattr(df, "empty") and not df.empty:
                        merged = df.merge(dart_data, on="ticker", how="left")
                        results[key] = _apply_canslim_c(key, dart_fetcher.add_valuation(merged))
                # 분기 재무 히스토리는 별도 컬렉션으로 저장 (재고 사이클/차트용)
                firebase_upload.save_fundamentals(histories)

        # 외인·기관 수급 (KR 전용) — 가격에서 파생되지 않은 유일한 독립 축
        if market_key == "kr" and investor_flow.available():
            print("\n외인·기관 순매수 수집 중...")
            try:
                results = investor_flow.attach(results, investor_flow.fetch())
            except Exception as e:
                print(f"  수급 수집 실패: {e}")

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

    # ── 실전 성적표 ────────────────────────────────────────
    # 과거에 화면에 떴던 종목들이 지금 얼마인지. 저장된 기록 + 방금 받은 시세만 쓰므로
    # 추가 조회가 없다.
    print("\n실전 성적표 계산 중...")
    try:
        scorecards = tracker.build(firebase_upload.get_db(), all_prices, list(configs))
    except Exception as e:
        print(f"  성적표 실패: {e}")
        scorecards = {}

    # ── Firebase 업로드 (스크리닝 결과 먼저) ───────────────
    # 백테스트가 잡 타임아웃에 걸리면 프로세스가 통째로 죽는다. 오늘 볼 종목이
    # 매일 돌 필요 없는 백테스트에 인질로 잡히지 않도록 먼저 올린다.
    firebase_upload.upload(all_market_results, run_type=run_type)
    firebase_upload.save_scorecard(scorecards)
    # 가상 매매 평가용 — 보유 종목이 패턴 목록에서 빠져도 현재가를 알 수 있어야 한다
    try:
        firebase_upload.save_prices(all_prices, all_names, all_meta)
    except Exception as e:
        print(f"  시세 업로드 실패: {e}")

    # ── 백테스트 (3개 시장 각각) ───────────────────────────
    # 스크리너 결과와 무관한 유니버스 표본을 스캔 — 선정된 종목만 되짚으면
    # 이미 오른 종목의 과거를 재는 셈이라 승률이 부풀려짐
    all_backtest = {}

    for market_key, cfg in configs.items():
        print(f"\n[{cfg['name']}] 백테스트 실행 중...")
        try:
            all_backtest[market_key] = backtest.run(cfg)
        except Exception as e:
            print(f"  백테스트 실패: {e}")
            all_backtest[market_key] = {}

    if any(all_backtest.values()):
        firebase_upload.attach_backtest(run_type, all_backtest)
    print("\nDone.")


if __name__ == "__main__":
    main()
