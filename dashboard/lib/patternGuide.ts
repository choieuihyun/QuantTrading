import type { PatternKey } from "./types";

export interface GuideRow {
  cond: string;
  ind: string;
  crit: string;
}

export interface PatternGuide {
  title: string;
  author?: string;
  tagline: string;
  concept?: string;
  composition?: string;
  conditions?: GuideRow[];
  scoring?: string;
  period?: string;
  note?: string;
}

// 원문: /패턴기법정리.md — 런타임 파싱 대신 하드코딩(기존 PATTERNS 인라인 문자열 관례와 동일)
export const PATTERN_GUIDE: Record<PatternKey, PatternGuide> = {
  common_trend: {
    title: "★ 추세 공통",
    tagline: "가장 높은 신뢰도 — 신고가형 상승 추세 종목",
    composition: "Stage 2 + CAN SLIM + Darvas Box 중 2개 이상 해당",
    concept:
      "세 가지 검증된 추세 추종 방법론이 동시에 가리키는 종목.\n이미 강한 추세가 형성된 모멘텀 추종형.",
    period: "스윙 ~ 중기 (4주 ~ 6개월)",
  },
  common_accum: {
    title: "★ 매집 공통",
    tagline: "가장 높은 신뢰도 — 폭발 직전 매집 완료 종목",
    composition: "Wyckoff + VCP 둘 다 해당",
    concept:
      "스마트머니 매집 + 변동성 수축이 동시에 포착된 종목.\n아직 크게 안 올랐지만 내부에서 매집 중 — 선행 진입형.",
    period: "중기 ~ 장기 (2개월 ~ 1년+)",
  },
  common_all: {
    title: "☆ 내 패턴 공통",
    tagline: "참고용 — 자체 개발 3패턴 중 2개 이상 해당",
    composition: "P1(정배열+매집) + P2(5일선추세) + P3(눌림목) 중 2개 이상",
    concept: "한국 시장 특성에 맞춘 단기~스윙 진입 신호.",
    period: "단기 스윙 (1~4주)",
  },
  canslim: {
    title: "CAN SLIM",
    author: "William O'Neil — IBD 창시자, 수십 년간 텐배거 발굴 방법론",
    tagline: "52주 신고가 + 거래량 폭발 + 상대강도 + EPS 성장",
    conditions: [
      { cond: "N — 신고가 근처", ind: "pos_52w", crit: "0.75 이상 (52주 고점 25% 이내)" },
      { cond: "S — 거래량 급증", ind: "vol_ratio", crit: "2배 이상" },
      { cond: "L — 시장 아웃퍼폼", ind: "rs", crit: "+5% 이상" },
      { cond: "M — 정배열", ind: "full_aligned", crit: "MA5 > MA20 > MA60 > MA120" },
      { cond: "C — EPS 성장 (DART)", ind: "canslim_c", crit: "전년 동기 대비 25%↑" },
    ],
    scoring: "신고가 근처 25 / 거래량 급증 30 / 상대강도 25 / 정배열 15 / RSI 5",
    note: "미구현: A(연간 EPS 3년 연속 25%↑), I(기관 신규 매수)",
  },
  vcp: {
    title: "VCP",
    author: "Mark Minervini — US 투자 챔피언십 우승, 연 200%+ 수익률",
    tagline: "변동성 수축 후 돌파 직전 (Volatility Contraction Pattern)",
    concept:
      "큰 조정(-30%) → 중간 조정(-20%) → 작은 조정(-10%) → 수축 완료 → 돌파\n거래량도 같이 수축 → 매물 소화 완료 신호",
    conditions: [
      { cond: "변동성 수축", ind: "bb_squeeze", crit: "볼린저 밴드 25% 이하 분위" },
      { cond: "조정 범위", ind: "pullback_pct", crit: "-10% ~ -30%" },
      { cond: "거래량 수축", ind: "vol_contracting", crit: "5일 평균 < 20일 평균 80%" },
      { cond: "정배열 유지", ind: "partial_aligned", crit: "MA5 > MA20 > MA60" },
      { cond: "매도세 없음", ind: "obv_rising", crit: "OBV 20일 전보다 높음" },
    ],
    scoring: "볼린저 수축 30 / 조정 범위 20 / 거래량 수축 15 / 정배열 20 / OBV 15",
  },
  stage2: {
    title: "Stage 2",
    author: "Stan Weinstein — 4단계 이론, 수십 년 시장 사이클 분석",
    tagline: "MA120 위 + 우상향 안정 추세 (상승 추세 진입 구간)",
    concept:
      "Stage 1: 횡보(바닥 다지기) → 관망\nStage 2: 상승 추세 진입 → ★ 매수 구간\nStage 3: 천장 횡보 → 매도 준비\nStage 4: 하락 → 절대 매수 금지",
    conditions: [
      { cond: "MA120(200) 위", ind: "price > ma120", crit: "현재가 > MA120" },
      { cond: "MA120 우상향", ind: "ma120_rising", crit: "현재 MA120 > 20일 전 MA120" },
      { cond: "Stage 2 안정 유지", ind: "above_ma120_days", crit: "최근 20일 중 15일 이상 MA120 위" },
      { cond: "정배열", ind: "partial_aligned", crit: "MA5 > MA20 > MA60" },
      { cond: "시장 아웃퍼폼", ind: "rs", crit: "RS > 0" },
    ],
    scoring: "MA120 위 25 / MA120 우상향 25 / 유지 기간 15 / 정배열 20 / RS 15",
  },
  wyckoff: {
    title: "Wyckoff 매집",
    author: "Richard Wyckoff — 100년 전 제시, 스마트머니 추적의 바이블",
    tagline: "OBV 신고점 = 스마트머니가 조용히 매수 중",
    concept:
      "PS(예비 지지) → SC(매도 절정) → AR(자동 반등) → ST(2차 테스트)\n→ Spring(최후 흔들기) → LPS(마지막 지지점) → SOS(강도 표시) → 상승",
    conditions: [
      { cond: "스마트머니 매집", ind: "obv_new_high", crit: "OBV 60일 최고점 98% 이상" },
      { cond: "OBV 상승 추세", ind: "obv_rising", crit: "OBV 20일 전보다 높음" },
      { cond: "Spring 후 수축", ind: "bb_squeeze", crit: "볼린저 수축 구간" },
      { cond: "매수 압력", ind: "bullish_ratio", crit: "최근 20일 양봉 65% 이상" },
      { cond: "MA 위 위치", ind: "price > ma20", crit: "현재가 > MA20" },
    ],
    scoring: "OBV 신고점 35 / OBV 상승 20 / 볼린저 수축 20 / 양봉 비율 15 / MA 위치 10",
  },
  darvas: {
    title: "Darvas Box",
    author: "Nicolas Darvas — 댄서 출신, 2년 만에 200만 달러 수익",
    tagline: "신고가 박스권 돌파 + 거래량 폭발",
    concept: "신고가 경신 → 일정 기간 박스권 형성 → 거래량 폭발과 함께 상단 돌파 → 매수",
    conditions: [
      { cond: "52주 신고가 근처", ind: "pos_52w", crit: "0.80 이상 (박스 상단 돌파 직후)" },
      { cond: "거래량 폭발", ind: "vol_ratio", crit: "2배 이상" },
      { cond: "강한 모멘텀", ind: "momentum_3m", crit: "15% 이상" },
    ],
    scoring: "52주 위치 35 / 거래량 폭발 40 / 모멘텀 25",
  },
  p1: {
    title: "정배열 퍼지기 직전 + 매집",
    tagline: "이평선이 막 정렬되려는 시점 + 스마트머니 매집 신호 포착",
    concept: "진입 논리: 정배열이 완성되기 직전이 가장 수익률이 높은 진입 타이밍",
    conditions: [
      { cond: "정배열 진행 중", ind: "partial_aligned", crit: "MA5 > MA20 > MA60" },
      { cond: "이평선 막 돌파", ind: "ma20_just_cross", crit: "MA20이 MA60을 최근 10일 내 돌파" },
      { cond: "볼린저 수축", ind: "bb_squeeze", crit: "폭발 직전 에너지 응축" },
      { cond: "OBV 상승", ind: "obv_rising", crit: "스마트머니 매집 중" },
      { cond: "OBV 신고점", ind: "obv_new_high", crit: "강한 매집 신호" },
      { cond: "양봉 우세", ind: "bullish_ratio", crit: "최근 20일 60% 이상 양봉" },
      { cond: "MACD 반등", ind: "macd_hist↑", crit: "히스토그램 증가 중" },
    ],
  },
  p2: {
    title: "5일선 추세 + 거래량 터짐",
    tagline: "5일선 이탈 없이 타고 올라가는 종목 (한국 시장 단기 추세 핵심)",
    concept: "진입 논리: 5일선 지지 + 거래량 급증 = 강한 추세 확인",
    conditions: [
      { cond: "완전 정배열", ind: "full_aligned", crit: "MA5 > MA20 > MA60 > MA120" },
      { cond: "5일선 위", ind: "price_above_ma5", crit: "현재가 > MA5" },
      { cond: "5일선 우상향", ind: "ma5_rising", crit: "MA5 상승 중" },
      { cond: "5일선 이탈 없음", ind: "no_ma5_break", crit: "최근 5일 종가 MA5 99% 이상 유지" },
      { cond: "MACD 강세", ind: "macd > signal", crit: "골든크로스 상태" },
      { cond: "RSI 건강", ind: "rsi", crit: "50~70 구간" },
      { cond: "거래량 터짐", ind: "vol_ratio", crit: "2배 이상" },
    ],
  },
  p3: {
    title: "눌림목",
    tagline: "상승 추세 중 일시적 조정 후 재진입 타이밍",
    concept: "진입 논리: 피보나치 되돌림 구간에서 MA20 지지 + MACD 반등 = 재상승 신호",
    conditions: [
      { cond: "조정 범위", ind: "is_pullback_range", crit: "고점 대비 -3% ~ -15%" },
      { cond: "피보나치 구간", ind: "in_fib_zone", crit: "38.2% ~ 61.8% 되돌림" },
      { cond: "MA20 지지", ind: "above_ma20", crit: "현재가 > MA20" },
      { cond: "반등 시작", ind: "today_bullish", crit: "오늘 양봉" },
      { cond: "MACD 바닥 반등", ind: "macd_hist↑", crit: "히스토그램 0선 아래서 증가" },
      { cond: "RSI 조정", ind: "rsi", crit: "35~55 구간" },
    ],
  },
};
