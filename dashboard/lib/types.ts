export interface Stock {
  ticker: string;
  name: string;
  market: string;
  price: number;
  ma5: number;
  ma20: number;
  ma60: number;
  ma120: number;
  rsi: number;
  macd: number;
  vol_ratio: number;
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
}

export type PatternKey = "p1" | "p2" | "p3" | "canslim" | "vcp" | "stage2" | "wyckoff" | "darvas" | "common";

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
  common: Stock[];
  p1_count: number;
  p2_count: number;
  p3_count: number;
  canslim_count: number;
  vcp_count: number;
  stage2_count: number;
  wyckoff_count: number;
  darvas_count: number;
  common_count: number;
}
