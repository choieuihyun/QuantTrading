export interface Stock {
  ticker: string;
  name: string;
  market: string;
  sector?: string;
  price: number;
  atr_14?: number;
  stop_swing?: number;
  stop_lt?: number;
  ma5: number;
  ma20: number;
  ma60: number;
  ma120: number;
  rsi: number;
  macd: number;
  vol_ratio: number;
  avg_value_20?: number;
  momentum_3m: number;
  rs?: number;
  pos_52w?: number;
  score: number;
  // P1
  bb_squeeze?: boolean;
  obv_rising?: boolean;
  obv_new_high?: boolean;
  bullish_ratio?: number;
  ma20_just_cross?: boolean;
  // P2
  full_aligned?: boolean;
  no_ma5_break?: boolean;
  // P3
  pullback_pct?: number;
  in_fib_zone?: boolean;
  above_ma20?: boolean;
  today_bullish?: boolean;
  // Stage2
  ma120_rising?: boolean;
  above_ma120_days?: number;
  // VCP
  vol_contracting?: boolean;
  partial_aligned?: boolean;
  // CAN SLIM / Darvas
  near_52w_high?: boolean;
  // Common
  pattern_hits?: number;
  // DART 펀더멘털 (KR만)
  marcap?: number;
  eps_current?: number;
  eps_yoy?: number;
  rev_yoy?: number;
  canslim_c?: boolean;
  // 밸류에이션 (= 시총 ÷ TTM 재무값)
  per?: number;
  pbr?: number;
  psr?: number;
  // 수익성·안정성 (비율은 0~1 소수, 예: 0.173 = 17.3%)
  roe?: number;
  roa?: number;
  op_margin?: number;
  net_margin?: number;
  debt_ratio?: number;
  // 재고 사이클
  inventory_qoq?: number;
  inventory_yoy?: number;
  inventory_turnover?: number;
  // CAPEX 사이클 — 투자 축소(capex_trend 음수)가 공급 조절 = 업황 반등 선행 신호
  capex_intensity?: number; // TTM CAPEX / TTM 매출
  capex_trend?: number; // 최근 4분기 CAPEX vs 직전 4분기
  fcf_margin?: number; // (영업CF − CAPEX) / 매출
  latest_period?: string;
  induty?: string; // KSIC 업종코드 (동종업계 비교용)
}

/** fundamentals/{ticker} — 분기 재무 원본 */
export interface QuarterRecord {
  y: number;
  q: number;
  rev?: number | null;
  cogs?: number | null;
  op?: number | null;
  net?: number | null;
  inventory?: number | null;
  assets?: number | null;
  liab?: number | null;
  equity?: number | null;
  receivables?: number | null;
  cash?: number | null;
}

export interface Fundamentals {
  corp_code: string;
  quarters: Record<string, QuarterRecord>;
}

export type MarketKey = "kr" | "us" | "crypto";
export type PatternKey = "p1" | "p2" | "p3" | "canslim" | "vcp" | "stage2" | "wyckoff" | "darvas" | "common_trend" | "common_accum" | "common_all";

export interface ScreenerResult {
  run_at: { seconds: number };
  market_date: string;
  run_type: string;
  p1: Stock[];
  p2: Stock[];
  p3: Stock[];
  canslim: Stock[];
  vcp: Stock[];
  stage2: Stock[];
  wyckoff: Stock[];
  darvas: Stock[];
  common_pro: Stock[];
  common_all: Stock[];
  [key: string]: Stock[] | unknown;
}
