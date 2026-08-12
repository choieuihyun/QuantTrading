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
    title: "★ 돌파 공통",
    tagline: "서로 다른 방식으로 '저항 돌파'를 확인한 종목",
    composition: "Stage 2 + CAN SLIM + Darvas + VCP 중 2개 이상 해당",
    concept:
      "네 기법 모두 '저항을 뚫는 순간'을 잡습니다 — 베이스 저항(Stage 2), 신고가(CAN SLIM),\n" +
      "박스 천장(Darvas), 피벗(VCP). 서로 다른 방식으로 같은 사건을 확인하면 신뢰도가 올라간다는 발상.",
    period: "스윙 ~ 중기 (4주 ~ 6개월)",
    note:
      "⚠️ 이미 오른 종목이 뜨는 게 정상입니다. 네 기법 전부 상승 추세를 전제로 하며, " +
      "특히 VCP·CAN SLIM은 52주 고점 25% 이내를 요구합니다. 실측: 선정 종목의 3개월 모멘텀 " +
      "중앙값 +53%(유니버스 +7%). 저평가 종목을 찾는 지표가 아닙니다.",
  },
  common_accum: {
    title: "★ 매집 공통",
    tagline: "거래범위 안에서 매집이 확인된 종목",
    composition: "Wyckoff 단독 (현재 구성 1개)",
    concept:
      "아직 크게 오르지 않았지만 거래범위 안에서 매도 압력이 마르고 있는 종목 — 선행 진입형.\n" +
      "돌파 공통과 정반대 국면을 봅니다.",
    period: "중기 ~ 장기 (2개월 ~ 1년+)",
    note:
      "원래 Wyckoff + VCP 둘 다였습니다. 원전 재구현 후 VCP가 Minervini Trend Template" +
      "(상승 추세)을 요구하게 되어 횡보 매집과 양립할 수 없게 됐습니다 — 둘을 AND로 묶으면 " +
      "영원히 비어 있습니다. VCP는 돌파 공통으로 옮겼습니다.",
  },
  common_all: {
    title: "☆ 내 패턴 공통",
    tagline: "자체 개발 3패턴 중 2개 이상 — 외부 검증 없음",
    composition: "P1(정배열+매집) + P2(5일선추세) + P3(눌림목) 중 2개 이상",
    concept:
      "한국 시장 특성에 맞춘 단기~스윙 진입 신호.\n" +
      "원전 기법과 달리 외부에서 검증된 방법론이 아니라 직접 정한 조건입니다.",
    period: "단기 스윙 (1~4주)",
    note:
      "신호 발생률이 12~15%로 원전 기법(1~5%)보다 훨씬 흔합니다 — 조건이 느슨하다는 뜻입니다. " +
      "실측 선정력은 20일 −0.35%, 60일 −0.01%로 유니버스와 비슷한 수준입니다.",
  },
  canslim: {
    title: "CAN SLIM",
    author: "William O'Neil — IBD 창시자",
    tagline: "신고가 + 거래량 + RS Rating 70↑ + 상승장에서만 매수",
    concept:
      "원전 7개 조건 중 N·S·L·M 4개를 구현했습니다.\n" +
      "L(주도주)은 IBD 방식 RS Rating — 코스피 대비 초과수익이 아니라 전 종목 백분위입니다.",
    conditions: [
      { cond: "N — 신고가 근처", ind: "pos_52w", crit: "0.75 이상 (52주 고점 25% 이내)" },
      { cond: "S — 거래량 급증", ind: "vol_ratio", crit: "20일 평균 2배 이상" },
      { cond: "L — 주도주", ind: "rs_rating", crit: "유니버스 백분위 70 이상 (IBD 기준)" },
      { cond: "M — 시장 방향", ind: "market_uptrend", crit: "지수가 자기 200일선 위 + 우상향" },
      { cond: "C — 현분기 EPS", ind: "canslim_c", crit: "전년 동기 대비 25%↑ (선정 후 가산 15점)" },
    ],
    scoring: "N 25 / L 30 / S 20 / M 15 / 추세건전성 10  → C 충족 시 +15",
    note:
      "⚠️ 미구현 — A(3년 연속 이익 증가): DART가 약 2년치만 제공. " +
      "I(기관 신규 매수): 외인·기관 순매수 데이터 미연동. " +
      "C는 유니버스 전체 재무를 못 받아 선정 단계가 아닌 사후 가산으로만 반영됩니다.",
  },
  vcp: {
    title: "VCP",
    author: "Mark Minervini — US 투자 챔피언십 우승",
    tagline: "조정이 연속으로 얕아지는 수축 + Trend Template 통과",
    concept:
      "큰 조정 → 중간 조정 → 작은 조정으로 '점점 얕아지는' 연속성이 VCP의 정체성입니다.\n" +
      "단순히 '지금 변동성이 낮다'는 것과 다릅니다.\n" +
      "Minervini Trend Template 8개를 먼저 통과해야 후보가 됩니다.",
    conditions: [
      { cond: "Trend Template", ind: "tt_ok", crit: "50/150/200일선 정렬·200일선 우상향·52주 저점 30%↑·고점 25% 이내" },
      { cond: "주도주", ind: "rs_rating", crit: "70 이상 (Trend Template 8번)" },
      { cond: "수축 횟수", ind: "vcp_legs", crit: "2회 이상 (교과서 2~5회)" },
      { cond: "점점 얕아짐", ind: "vcp_tightening", crit: "각 조정이 직전보다 작음" },
      { cond: "거래량 감소", ind: "vcp_vol_declining", crit: "수축마다 평균 거래량 감소" },
      { cond: "피벗 돌파", ind: "vcp_above_pivot", crit: "마지막 수축 고점 상향" },
    ],
    scoring: "점점 얕아짐 30 / 수축 3회↑ 15 / 거래량 감소 20 / 마지막 수축 타이트 20 / 피벗 돌파 15",
    note:
      "근사 — 스윙 고·저점을 좌우 5봉 기준으로 잡고 최근 90봉에서 수축을 찾습니다. " +
      "'어느 스윙을 한 번의 수축으로 셀지'는 원전에 수치가 없어 임의로 정한 부분입니다.",
  },
  stage2: {
    title: "Stage 2",
    author: "Stan Weinstein — 4단계 이론",
    tagline: "30주선 위 + 우상향 + 베이스 저항을 거래량 동반 돌파",
    concept:
      "Stage 1: 횡보(바닥) → Stage 2: 상승 전환 ★매수 → Stage 3: 천장 → Stage 4: 하락\n" +
      "핵심은 '이미 오르는 상태'가 아니라 베이스 저항을 뚫는 '전환 시점'입니다.",
    conditions: [
      { cond: "30주선 위", ind: "price > ma150", crit: "현재가 > 150일선 (30주 ≈ 150거래일)" },
      { cond: "30주선 우상향", ind: "ma150_rising", crit: "21거래일 전보다 높음" },
      { cond: "베이스 저항 돌파", ind: "base_breakout", crit: "횡보 구간 상단 상향 (최근 10봉 내 인정)" },
      { cond: "돌파 거래량", ind: "breakout_vol", crit: "돌파 봉 거래량 평균 2배 이상" },
      { cond: "주도주", ind: "rs_rating", crit: "70 이상 우대" },
    ],
    scoring: "30주선 위 20 / 우상향 20 / 돌파 20 / 돌파 거래량 20 / RS 12 / 200일선 위 8",
    note:
      "근사 — 원전은 주봉 30주선입니다. 여기서는 일봉 150선으로 대체했습니다(30주 = 150거래일). " +
      "베이스는 최근 최대 120봉 중 폭 30% 이내로 횡보한 구간을 자동 인식합니다.",
  },
  wyckoff: {
    title: "Wyckoff 매집",
    author: "Richard Wyckoff — 스마트머니 추적의 원류",
    tagline: "거래범위 안에서 Spring 또는 SOS + 하락일 거래량 소진",
    concept:
      "PS → SC(매도절정) → AR → ST → Spring(최후 흔들기) → LPS → SOS(강도 표시) → 상승\n" +
      "이 중 구조로 확인 가능한 Spring·SOS·거래량 소진만 구현했습니다.",
    conditions: [
      { cond: "거래범위 존재", ind: "range_high/low", crit: "폭 30% 이내로 20봉 이상 횡보" },
      { cond: "Spring", ind: "wyckoff_spring", crit: "하단을 저가로 이탈했다가 종가 회복" },
      { cond: "SOS", ind: "wyckoff_sos", crit: "거래량 2배 동반 상단 돌파" },
      { cond: "매도 소진", ind: "wyckoff_vol_dry", crit: "하락일 평균 거래량 < 상승일" },
      { cond: "OBV 상승", ind: "obv_rising", crit: "20일 전보다 높음" },
    ],
    scoring: "Spring 30 / SOS 30 / 매도 소진 20 / OBV 상승 12 / OBV 신고점 8",
    note:
      "⚠️ 부분 구현 — 국면(Phase A~E) 판정과 SC/AR/ST 식별은 거래량-스프레드 재량 해석이라 " +
      "코드로 옮기지 않았습니다. 'Wyckoff 방법론'이 아니라 그중 기계적으로 확인 가능한 일부입니다.",
  },
  darvas: {
    title: "Darvas Box",
    author: "Nicolas Darvas — 2년 만에 200만 달러",
    tagline: "박스 천장 돌파 + 거래량. 손절은 박스 바닥",
    concept:
      "신고가가 3봉 동안 경신되지 않으면 그 고가가 박스 천장.\n" +
      "이후 최저가가 3봉을 버티면 박스 바닥. 천장을 종가로 넘으면 매수.",
    conditions: [
      { cond: "박스 천장 확정", ind: "box_top", crit: "신고가가 3봉간 미경신" },
      { cond: "박스 바닥 확정", ind: "box_bottom", crit: "이후 최저가가 3봉간 미이탈" },
      { cond: "박스 폭", ind: "box_top/bottom", crit: "25% 이내 (넘으면 횡보가 아닌 추세)" },
      { cond: "천장 돌파", ind: "box_breakout", crit: "종가 > 박스 천장" },
      { cond: "거래량", ind: "vol_ratio", crit: "20일 평균 2배 이상" },
    ],
    scoring: "천장 돌파 35 / 거래량 25 / 박스 폭 20 / 52주 위치 20",
    note:
      "손절은 ATR이 아니라 박스 바닥(stop_box)을 씁니다 — 원전 규칙입니다. " +
      "박스 폭 상한 25%는 원전에 수치가 없어 임의로 정했습니다(하락 추세 전체가 박스로 잡히는 것 방지).",
  },
  p1: {
    title: "정배열 퍼지기 직전 + 매집",
    tagline: "이평선이 막 정렬되려는 시점 + 스마트머니 매집 신호 포착",
    concept:
      "진입 논리: 정배열이 완성되기 직전이 가장 수익률이 높은 진입 타이밍.\n" +
      "필수조건 — 부분 정배열 + (OBV 상승 또는 볼린저 수축). 나머지는 가산점입니다.",
    conditions: [
      { cond: "정배열 진행 중", ind: "partial_aligned", crit: "MA5 > MA20 > MA60" },
      { cond: "이평선 막 돌파", ind: "ma20_just_cross", crit: "MA20이 MA60을 최근 10일 내 돌파" },
      { cond: "볼린저 수축", ind: "bb_squeeze", crit: "폭발 직전 에너지 응축" },
      { cond: "OBV 상승", ind: "obv_rising", crit: "스마트머니 매집 중" },
      { cond: "OBV 신고점", ind: "obv_new_high", crit: "강한 매집 신호" },
      { cond: "양봉 우세", ind: "bullish_ratio", crit: "최근 20일 60% 이상 양봉" },
      { cond: "MACD 반등", ind: "macd_hist↑", crit: "히스토그램 증가 중" },
    ],
    scoring: "정배열 20 / MA20 돌파 15 / MA60 돌파 10 / 볼린저 수축 20 / OBV 상승 15 / OBV 신고점 10 / 양봉 10 / MACD 반등 10 / RSI 5 / 거래량 5",
    note:
      "필수조건: 부분 정배열 + (OBV 상승 또는 볼린저 수축). " +
      "⚠️ RSI를 표준(Wilder 평활)으로 정정하면서 이 패턴의 RSI 구간 판정이 바뀔 수 있습니다 — " +
      "실측 60종목 중 15종목에서 게이트 판정이 뒤집혔습니다. 임계값(50~70, 35~55)은 " +
      "옛 RSI 기준으로 정해진 값이라 재검토가 필요합니다.",

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
    scoring: "완전 정배열 20 / 5일선 위 10 / 5일선 우상향 10 / 이탈 없음 10 / MACD 0선 위 10 / 골든크로스 10 / 히스토그램 5 / RSI 10 / 거래량 10+5 / OBV 5 / 모멘텀 5",
    note:
      "필수조건: 완전 정배열 + 5일선 위 + MACD > 0. " +
      "⚠️ RSI를 표준(Wilder 평활)으로 정정하면서 이 패턴의 RSI 구간 판정이 바뀔 수 있습니다 — " +
      "실측 60종목 중 15종목에서 게이트 판정이 뒤집혔습니다. 임계값(50~70, 35~55)은 " +
      "옛 RSI 기준으로 정해진 값이라 재검토가 필요합니다.",

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
    scoring: "조정 범위 25 / 피보나치 20 / MA20 지지 15 / 오늘 양봉 10 / 정배열 10 / MACD 바닥 반등 10 / RSI 10",
    note:
      "필수조건: 조정 범위 + MA20 위. " +
      "⚠️ RSI를 표준(Wilder 평활)으로 정정하면서 이 패턴의 RSI 구간 판정이 바뀔 수 있습니다 — " +
      "실측 60종목 중 15종목에서 게이트 판정이 뒤집혔습니다. 임계값(50~70, 35~55)은 " +
      "옛 RSI 기준으로 정해진 값이라 재검토가 필요합니다.",

  },
};
