"""
시장별 설정값 — 스크리닝 임계값, 데이터 소스, 벤치마크 정의
"""

KR_CONFIG = {
    "type":            "KR",
    "name":            "한국 (KOSPI/KOSDAQ)",
    "markets":         ["KOSPI", "KOSDAQ"],
    "benchmark":       "KS11",
    "min_marcap":      100_000_000_000,   # 1000억 KRW
    "skip_weekends":   True,
    "currency":        "KRW",
    # 스코어링 임계값
    "score_threshold": 40,
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
    "score_threshold": 40,
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
    # 높은 변동성 반영
    "score_threshold": 35,
    "vol_ratio_buy":   3.0,               # 더 높은 기준
    "vol_ratio_surge": 5.0,
    "momentum_min":    0.10,              # 10%+ (코인은 더 크게 움직임)
    "pullback_min":    -0.30,             # 더 넓은 눌림목 범위
    "pullback_max":    -0.05,
    "vcp_pullback_min": -0.50,            # 더 넓은 VCP 범위
    "vcp_pullback_max": -0.15,
    "rsi_min":         45,
    "rsi_max":         75,
    "rsi_overbought":  85,
    "rsi_pb_min":      30,
    "rsi_pb_max":      55,
}

CRYPTO_TICKERS = [
    "BTC/USD", "ETH/USD", "BNB/USD", "SOL/USD", "XRP/USD",
    "ADA/USD", "AVAX/USD", "DOT/USD", "MATIC/USD", "LINK/USD",
    "UNI/USD", "ATOM/USD", "LTC/USD", "BCH/USD", "NEAR/USD",
    "APT/USD", "OP/USD",  "ARB/USD", "DOGE/USD", "TRX/USD",
    "TON/USD", "SUI/USD", "INJ/USD", "FIL/USD",  "HBAR/USD",
]

ALL_CONFIGS = {
    "kr":     KR_CONFIG,
    "us":     US_CONFIG,
    "crypto": CRYPTO_CONFIG,
}
