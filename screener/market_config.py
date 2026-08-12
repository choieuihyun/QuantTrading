"""
시장별 설정값 — 스크리닝 임계값, 데이터 소스, 벤치마크, 거래비용 정의
"""

KR_CONFIG = {
    "type":            "KR",
    "name":            "한국 (KOSPI/KOSDAQ)",
    "markets":         ["KOSPI", "KOSDAQ"],
    "benchmark":       "KS11",
    "min_marcap":      100_000_000_000,   # 1000억 KRW
    "skip_weekends":   True,
    "currency":        "KRW",

    # ── 데이터 기간 ───────────────────────────────────────
    "data_days":       480,               # lookback_bars(300봉)를 휴장일 포함해도 확보
    "bt_days":         1100,              # 백테스트 스캔 구간 확보
    "bars_per_year":   252,               # pos_52w 계산 기준 봉 수
    "lookback_bars":   300,               # 신호 계산에 쓰는 봉 수 — 라이브/재현 공통
    "drop_partial_bar": False,            # 장 마감 후 실행 → 완성봉

    # ── 유동성 / 거래가능성 ───────────────────────────────
    "min_trading_value": 1_000_000_000,   # 20일 평균 거래대금 10억 KRW
    "exclude_name_patterns": "스팩|리츠",
    "common_stock_only": True,            # 종목코드 끝자리 0 = 보통주

    # ── 거래비용 (백테스트 반영) ──────────────────────────
    "fee_rate":        0.00015,           # 위탁수수료 (편도)
    "tax_rate":        0.0018,            # 증권거래세 (매도시) — 세율 변경시 조정
    "slippage":        0.001,             # 호가 슬리피지 (편도)

    # ── 스코어링 임계값 ───────────────────────────────────
    "score_threshold": 60,
    "vol_ratio_buy":   2.0,
    "vol_ratio_surge": 3.0,
    "momentum_min":    0.05,
    "pullback_min":    -0.15,
    "pullback_max":    -0.03,
    "vcp_pullback_min": -0.30,
    "vcp_pullback_max": -0.10,
    "rsi_min":         50,
    "rsi_max":         70,
    "rsi_overbought":  80,
    "rsi_pb_min":      35,
    "rsi_pb_max":      55,
}

US_CONFIG = {
    "type":            "US",
    "name":            "미국 (S&P 500)",
    "markets":         ["S&P500"],
    "benchmark":       "SPY",
    "min_marcap":      None,              # S&P500 자체가 대형주 필터
    "skip_weekends":   True,
    "currency":        "USD",

    "data_days":       480,
    "bt_days":         1100,
    "bars_per_year":   252,
    "lookback_bars":   300,
    "drop_partial_bar": False,

    "min_trading_value": 10_000_000,      # 20일 평균 거래대금 $10M
    "exclude_name_patterns": None,
    "common_stock_only": False,

    "fee_rate":        0.0,               # 미국 온라인 브로커 대부분 무료
    "tax_rate":        0.0,
    "slippage":        0.0005,

    "score_threshold": 60,
    "vol_ratio_buy":   2.0,
    "vol_ratio_surge": 3.0,
    "momentum_min":    0.05,
    "pullback_min":    -0.15,
    "pullback_max":    -0.03,
    "vcp_pullback_min": -0.30,
    "vcp_pullback_max": -0.10,
    "rsi_min":         50,
    "rsi_max":         70,
    "rsi_overbought":  80,
    "rsi_pb_min":      35,
    "rsi_pb_max":      55,
}

CRYPTO_CONFIG = {
    "type":            "CRYPTO",
    "name":            "암호화폐 (Top 30)",
    "markets":         ["CRYPTO"],
    "benchmark":       "BTC/USD",
    "min_marcap":      None,
    "skip_weekends":   False,             # 24/7 시장
    "currency":        "USD",

    "data_days":       500,               # 24/7이라 1년 = 365봉
    "bt_days":         1100,
    "bars_per_year":   365,
    "lookback_bars":   420,               # 365봉(1년) + 여유
    "drop_partial_bar": True,             # 진행 중인 당일 봉은 거래량이 미완성

    "min_trading_value": 50_000_000,      # 20일 평균 거래대금 $50M
    "exclude_name_patterns": None,
    "common_stock_only": False,

    "fee_rate":        0.001,             # 테이커 0.1% (편도)
    "tax_rate":        0.0,
    "slippage":        0.002,

    # 높은 변동성 반영
    "score_threshold": 55,
    "vol_ratio_buy":   3.0,
    "vol_ratio_surge": 5.0,
    "momentum_min":    0.10,
    "pullback_min":    -0.30,
    "pullback_max":    -0.05,
    "vcp_pullback_min": -0.50,
    "vcp_pullback_max": -0.15,
    "rsi_min":         45,
    "rsi_max":         75,
    "rsi_overbought":  85,
    "rsi_pb_min":      30,
    "rsi_pb_max":      55,
}

CRYPTO_TICKERS = [
    "BTC/USD",  "ETH/USD",  "BNB/USD",  "SOL/USD",  "XRP/USD",
    "ADA/USD",  "AVAX/USD", "DOT/USD",  "POL/USD",  "LINK/USD",
    "UNI/USD",  "ATOM/USD", "LTC/USD",  "BCH/USD",  "NEAR/USD",
    "APT/USD",  "OP/USD",   "ARB/USD",  "DOGE/USD", "TRX/USD",
    "TON/USD",  "SUI/USD",  "INJ/USD",  "FIL/USD",  "HBAR/USD",
    "AAVE/USD", "ALGO/USD", "VET/USD",  "XLM/USD",  "ETC/USD",
]

ALL_CONFIGS = {
    "kr":     KR_CONFIG,
    "us":     US_CONFIG,
    "crypto": CRYPTO_CONFIG,
}
