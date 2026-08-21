export interface Stock {
  /** 외국인·기관 순매수 (KR 전용). 시총 대비 비율(_pct)이 종목 간 비교 가능한 값이다 */
  foreign_net_20d?: number | null;
  inst_net_20d?: number | null;
  foreign_net_60d?: number | null;
  inst_net_60d?: number | null;
  foreign_net_20d_pct?: number | null;
  inst_net_20d_pct?: number | null;
  foreign_net_60d_pct?: number | null;
  inst_net_60d_pct?: number | null;

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
  /** IBD 방식 RS Rating(1~99) — 유니버스 백분위. O'Neil의 L 기준은 70 이상 */
  rs_rating?: number;
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
  // Stage2 (Weinstein) — 30주선(=150일선) + 베이스 저항 돌파
  ma120_rising?: boolean;
  above_ma120_days?: number;
  ma150?: number;
  ma150_rising?: boolean;
  range_high?: number | null;
  range_low?: number | null;
  base_breakout?: boolean;
  /** 돌파 봉의 거래량 배수 — Weinstein은 평균 2배 이상 요구 */
  breakout_vol?: number;
  // VCP (Minervini) — Trend Template + 연속 수축
  vol_contracting?: boolean;
  partial_aligned?: boolean;
  /** Trend Template 7개 충족 (8번 RS Rating은 별도) */
  tt_ok?: boolean;
  vcp_legs?: number;
  vcp_last_depth?: number | null;
  vcp_pivot?: number | null;
  vcp_above_pivot?: boolean;
  // Darvas — 박스 천장/바닥. 손절은 ATR이 아니라 박스 바닥
  box_top?: number | null;
  box_bottom?: number | null;
  stop_box?: number | null;
  box_bars?: number;
  // Wyckoff — 구조적으로 확인 가능한 부분만
  wyckoff_spring?: boolean;
  wyckoff_sos?: boolean;
  wyckoff_vol_dry?: boolean;
  // CAN SLIM / Darvas
  near_52w_high?: boolean;
  /** CAN SLIM M — 벤치마크가 자기 200일선 위 + 우상향 */
  market_uptrend?: boolean;
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

/** replay_results/{market} — 과거 재현: 상위 N종목 리스트를 통째로 샀을 때의 성과 */
export interface ReplayStat {
  pattern: string;
  hold: number;
  top_k: number;
  threshold?: number;
  n_dates: number;
  n_picks: number;
  avg_picks_per_date?: number;
  no_stop?: boolean;
  /** 상위 N종목 동일가중 수익률 (비용 반영, 스캔일 평균) */
  port_return?: number;
  bench_return?: number;
  /** 그날 유동성을 통과한 전 종목의 동일가중 평균 */
  uni_return?: number;
  excess_return?: number;
  excess_median?: number;
  /** 종목 선정 실력 = 리스트 − 유니버스. 지수는 시총가중이라 가중방식 차이가 섞임 */
  excess_uni?: number;
  uni_hit_rate?: number;
  /** 벤치마크를 이긴 '날짜'의 비율 — 종목 단위로 세면 같은 날이 N표가 되어 과대평가됨 */
  date_hit_rate?: number;
  name_hit_rate?: number;
  /** 상위 N이 전부 동점이었던 날의 비율. 높으면 순위·RankIC를 해석하면 안 됨 */
  tie_ratio?: number;
  best_date?: string;
  worst_date?: string;
  worst_excess?: number;
  stop_hit_rate?: number;
  /** 보유 중 상장폐지되어 마지막 체결가로 청산된 건수 */
  delisted_exits?: number;
  rank_buckets?: Record<string, number>;
  /** 스코어 순위와 실제 수익률 순위의 상관 — 0에 가까우면 정렬이 무의미 */
  rank_ic?: number | null;
}

export interface ReplayGrid {
  market: string;
  generated_at: string;
  date_from: string;
  date_to: string;
  panel_rows: number;
  n_tickers: number;
  n_dates: number;
  threshold: number;
  holds: number[];
  tops: number[];
  costs: { fee_rate: number; tax_rate: number; slippage: number };
  /** 키 형식: "{pattern}|{hold}|{top_k}" */
  results: Record<string, ReplayStat>;
}

/**
 * scorecard/{market}_{date} — 실전 성적표.
 * 재구성이 아니라 그날 화면에 실제로 떴던 기록 + 오늘 가격. 하루 2회 자동 갱신.
 */
export interface ScorePick {
  ticker: string;
  name: string;
  score?: number;
  /** 그날 화면에 표시됐던 가격 */
  entry?: number;
  /** 오늘 가격. 상장폐지·거래정지로 오늘 유니버스에 없으면 null */
  now?: number | null;
  ret?: number | null;
  stop_swing?: number;
  rsi?: number;
  pos_52w?: number;
  gone?: boolean;
  /** 진입일 이후 액면분할·무상증자 등 자본 조정이 있었던 종목.
   *  수익률은 조정 후 시계열로 다시 계산했지만 score·rsi·pos_52w는 조정 전 기준이다 */
  adjusted?: boolean;
  /** 그날 화면에 떴던 원래 가격 (조정 전) */
  stored_entry?: number | null;
}

export interface ScorePattern {
  picks: ScorePick[];
  n: number;
  gone: number;
  /** 자본 조정이 있었던 종목 수 */
  adjusted?: number;
  avg?: number | null;
  median?: number | null;
  wins: number;
  best?: number | null;
  worst?: number | null;
}

export interface ScorecardDoc {
  market: string;
  date: string;
  patterns: Record<string, ScorePattern>;
}

export interface ScorecardIndex {
  market: string;
  updated_at: string;
  price_date: string;
  patterns: string[];
  dates: { date: string; days_ago: number }[];
}

/** replay_picks/{market}_{date} — 그날 그 패턴 리스트에 있던 종목별 손익 */
export interface ReplayPick {
  rank: number;
  ticker: string;
  name: string;
  score: number;
  /** 신호일 종가 */
  price: number;
  /** 실제 매수가 = 신호 다음날 시가 */
  entry: number;
  rsi: number;
  vol_ratio: number;
  pos_52w: number;
  stop_swing: number;
  /** 안 팔고 현재까지 보유했을 때의 수익률 (비용 반영) */
  ret_now: number;
  last_close: number;
  held_bars: number;
  /** 보유 중 ATR 손절선을 건드린 적 있는지 (청산하진 않음) */
  touched_stop: boolean;
  /** 고정 보유기간 — 아직 기간이 안 지났으면 null */
  ret_5?: number | null;
  ret_20?: number | null;
  ret_60?: number | null;
  stop_5?: boolean | null;
  stop_20?: boolean | null;
  stop_60?: boolean | null;
}

export interface ReplayPickSummary {
  n: number;
  port?: number;
  uni?: number | null;
  bench?: number;
  wins?: number;
}

export interface ReplayPickDoc {
  market: string;
  date: string;
  top_k: number;
  threshold: number;
  /** 키: 패턴명 */
  patterns: Record<string, { summary: Record<string, ReplayPickSummary>; picks: ReplayPick[] }>;
}

export interface ReplayPickIndex {
  market: string;
  generated_at: string;
  top_k: number;
  threshold: number;
  holds: number[];
  dates: { date: string; bars_ago: number }[];
  latest_bar: string;
}

export interface ScreenerResult {
  run_at: { seconds: number };
  market_date: string;
  run_type: string;
  /** 150일선 위 종목 비율. 지수보다 장세를 정확히 말해준다 */
  kr_breadth?: number | null;
  us_breadth?: number | null;
  crypto_breadth?: number | null;
  kr_bar_date?: string;
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

/** prices/{market} — 유니버스 전 종목 시세. 가상 매매 평가용(하루 2회 갱신) */
export interface PriceDoc {
  market_date: string;
  run_at: { seconds: number };
  count: number;
  prices: Record<string, number>;
  names: Record<string, string>;
}

/** 가상 매매 보유 기록. 브라우저 localStorage에만 저장된다 — 서버에 쓰지 않는다 */
export interface Position {
  id: string;
  market: MarketKey;
  ticker: string;
  name: string;
  /** 담은 날 (YYYY-MM-DD) */
  entryDate: string;
  entryPrice: number;
  shares: number;
  /** 어느 화면에서 담았는지 — 패턴별 성적을 나중에 되짚기 위해 */
  pattern?: PatternKey | null;
  note?: string;
  /** 청산했으면 기록. 남겨둬야 '팔았으면 얼마였나'를 볼 수 있다 */
  exitDate?: string | null;
  exitPrice?: number | null;
}

/** signals/{market}_index — 종목 조회용 메타. 조건 라벨은 종목마다 같아 여기 한 번만 둔다 */
export interface SignalIndex {
  bar_date: string;
  run_at: { seconds: number };
  threshold: number;
  shards: number;
  count: number;
  /** 패턴 → 게이트 조건 라벨. 종목 데이터의 조건 배열과 순서가 1:1 대응한다 */
  labels: Record<string, string[]>;
}

export type SignalState = "x" | "g" | "l" | "p";

/** Firestore는 배열 안에 배열을 못 담아 조건을 맵의 배열로 둔다 (o=통과, d=실측값) */
export interface SignalCond { o: boolean; d: string }

/** 원전이 정한 진입 기준점. pv=피벗 gap=현재가와의 거리 st=원전 손절 sg=손절까지 거리 */
export interface EntryRef {
  pv: number; lb: string; gap: number; pd?: string; st?: number; sg?: number;
}

export interface SignalEntry {
  s: SignalState;
  v: number;
  e?: EntryRef;
  /** 게이트 조건. 인덱스 문서의 labels[pattern]과 순서가 1:1 대응한다 */
  c?: SignalCond[];
  /** common_* 전용 — 통과한 구성 패턴 목록 */
  h?: string[];
}

export interface SignalRow {
  /** 대상 제외 사유. 있으면 패턴 판정 자체를 안 한다 */
  x?: string;
  p?: Record<string, SignalEntry>;
}

export interface SignalShard {
  bar_date: string;
  /** 색인 항목 한도(문서당 4만) 때문에 JSON 문자열로 담는다.
   *  전환 이전 실행이 남긴 문서는 tickers(맵)를 갖고 있어 둘 다 받는다. */
  tickers_json?: string;
  tickers?: Record<string, SignalRow>;
}

/** flows/{market} — KRX 수급·공매도·밸류에이션. 로컬 실행(enrich_local.py)에서만 채워진다 */
export interface FlowRow {
  /** 시총 대비 (%) */
  f20?: number; i20?: number; f60?: number; i60?: number;
  /** 절대 순매수 (억원). 비율만 보면 대형주가 구조적으로 낮게 나온다 */
  f20v?: number; i20v?: number; f60v?: number; i60v?: number;
  sv?: number; sb?: number;
  per?: number; pbr?: number; div?: number; eps?: number;
}
export interface FlowDoc {
  bar_date: string;
  count: number;
  /** 짧은 키의 뜻 — 문서에 함께 저장된다 */
  legend: Record<string, string>;
  /** 지표별 0~100 분위 경계값(101개). 종목마다 백분위를 저장하지 않고 여기서 찾는다 */
  dist?: Record<string, number[]>;
  /** 종목별 데이터를 JSON 문자열로 담는다 — 맵으로 두면 색인 항목이 문서 한도(4만)를 넘는다 */
  tickers_json?: string;
  tickers?: Record<string, FlowRow>;
}

/** disclosures/{market} — DART 공시. lv: c=자본조정(무상증자·분할) / m=중요공시 */
export interface DisclosureItem { d: string; nm: string; lv: "c" | "m"; no: string }
export interface DisclosureRow { items: DisclosureItem[]; dropped: number; from: string }
export interface DisclosureDoc {
  bar_date: string;
  count: number;
  /** 위와 같은 이유로 JSON 문자열 */
  tickers_json?: string;
  tickers?: Record<string, DisclosureRow>;
}

/** watchlist/{market} — 아직 발동하지 않은 패턴의 발동가. 매수 신호가 아니다. */
export interface WatchRow {
  t: string; n: string;
  /** 패턴 키 — 무엇을 기다리는 중인지 */
  k: string;
  lb: string; ef: string;
  pr: number; tg: number; g: number;
  st?: number | null; sl?: number | null; rs?: number | null;
}
export interface WatchDoc {
  bar_date: string;
  count: number;
  rows_json?: string;
  rows?: WatchRow[];
}
