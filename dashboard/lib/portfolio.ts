import type { MarketKey, PatternKey, Position } from "./types";

/**
 * 가상 매매 보유 기록 — 브라우저 localStorage에만 저장한다.
 *
 * Firestore에 쓰지 않는 이유: 이 프로젝트에는 로그인이 없다. 규칙에서 쓰기를 열면
 * 주소만 알면 누구나 남의 포트폴리오를 지우거나 조작할 수 있다. 개인용 기록이라
 * 브라우저에 두는 편이 안전하고, Actions는 읽기 전용 시세만 올리면 된다.
 *
 * 대가: 브라우저를 바꾸면 기록이 따라오지 않는다. 그래서 내보내기/가져오기를 둔다.
 */

const KEY = "qt.portfolio.v1";

/**
 * 왕복 거래비용 — screener/market_config.py와 같은 값이어야 한다.
 * 성적표·3년치 통계는 비용을 뺀 수익률을 보여준다. 여기만 세전으로 두면
 * 두 화면 숫자를 나란히 놓고 잘못 비교하게 된다.
 */
const COST: Record<MarketKey, { fee: number; tax: number; slip: number }> = {
  kr:     { fee: 0.00015, tax: 0.0018, slip: 0.001  },
  us:     { fee: 0,       tax: 0,      slip: 0.0005 },
  crypto: { fee: 0.001,   tax: 0,      slip: 0.002  },
};

/** 진입가는 비용만큼 비싸게, 청산가는 비용만큼 싸게 친다 (replay._forward_outcomes와 동일) */
function afterCost(market: MarketKey, entry: number, exit: number) {
  const c = COST[market] ?? COST.kr;
  return {
    entry: entry * (1 + c.fee + c.slip),
    exit: exit * (1 - c.fee - c.slip - c.tax),
  };
}

export function roundTripCost(market: MarketKey): number {
  const c = COST[market] ?? COST.kr;
  return 2 * (c.fee + c.slip) + c.tax;
}

function isPosition(v: unknown): v is Position {
  if (!v || typeof v !== "object") return false;
  const p = v as Record<string, unknown>;
  return (
    typeof p.id === "string" &&
    typeof p.ticker === "string" &&
    typeof p.entryDate === "string" &&
    typeof p.entryPrice === "number" &&
    Number.isFinite(p.entryPrice) &&
    typeof p.shares === "number" &&
    Number.isFinite(p.shares)
  );
}

export function load(): Position[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    // 손상된 항목 하나가 화면 전체를 죽이지 않도록 개별 검사 후 통과분만 쓴다
    return Array.isArray(parsed) ? parsed.filter(isPosition) : [];
  } catch {
    return [];
  }
}

export function save(list: Position[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(KEY, JSON.stringify(list));
}

export function newId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * 손으로 입력한 매수가는 그 뒤 액면분할·무상증자가 있어도 자동으로 조정되지 않는다.
 * 현재가와 배율이 정수배에 가까우면 자본 조정을 의심한다 — 사용자가 넣은 값을
 * 말없이 고쳐 쓰지는 않고 확인만 요청한다.
 */
export function suspectSplit(entry: number, now: number | null): number | null {
  if (!now || entry <= 0) return null;
  for (const k of [2, 3, 4, 5, 10, 0.5, 0.2, 0.1]) {
    if (Math.abs(entry / now / k - 1) < 0.06) return k;
  }
  return null;
}

export interface Valued extends Position {
  /** 평가에 쓴 현재가. 시세에 없으면 null */
  nowPrice: number | null;
  /** 왕복 거래비용을 뺀 수익률 — 성적표·통계 화면과 같은 기준 */
  pnlPct: number | null;
  pnlAmount: number | null;
  /** 비용 반영 전. 두 값의 차이가 곧 비용이다 */
  grossPct: number | null;
  cost: number;
  value: number | null;
  heldDays: number;
  closed: boolean;
  /** 자본 조정 의심 배율. null이면 정상 */
  splitFactor: number | null;
}

export function valuePosition(p: Position, prices: Record<string, number>): Valued {
  const closed = Boolean(p.exitDate && p.exitPrice);
  const mark = closed ? p.exitPrice! : (prices[p.ticker] ?? null);
  const cost = p.entryPrice * p.shares;
  const value = mark === null ? null : mark * p.shares;
  const end = closed ? new Date(p.exitDate!) : new Date();
  const heldDays = Math.max(
    0,
    Math.round((end.getTime() - new Date(p.entryDate).getTime()) / 86_400_000)
  );
  let pnlPct: number | null = null;
  let pnlAmount: number | null = null;
  if (mark !== null && p.entryPrice > 0) {
    const eff = afterCost(p.market, p.entryPrice, mark);
    pnlPct = (eff.exit - eff.entry) / eff.entry;
    pnlAmount = pnlPct * cost;
  }
  return {
    ...p,
    closed,
    nowPrice: mark,
    cost,
    value,
    pnlPct,
    pnlAmount,
    grossPct: mark === null || p.entryPrice <= 0 ? null : (mark - p.entryPrice) / p.entryPrice,
    heldDays,
    splitFactor: closed ? null : suspectSplit(p.entryPrice, mark),
  };
}

export interface Totals {
  cost: number;
  value: number;
  pnlAmount: number;
  pnlPct: number | null;
  /** 현재가를 못 찾은 보유 건수 — 있으면 합계가 불완전하다는 뜻 */
  unpriced: number;
  wins: number;
  losses: number;
}

export function totals(rows: Valued[]): Totals {
  let cost = 0, pnlAmount = 0, unpriced = 0, wins = 0, losses = 0;
  for (const r of rows) {
    if (r.pnlAmount === null) { unpriced += 1; continue; }
    cost += r.cost;
    pnlAmount += r.pnlAmount;
    if (r.pnlPct !== null && r.pnlPct > 0) wins += 1;
    else if (r.pnlPct !== null && r.pnlPct < 0) losses += 1;
  }
  return {
    cost, unpriced, wins, losses, pnlAmount,
    value: cost + pnlAmount,
    pnlPct: cost > 0 ? pnlAmount / cost : null,
  };
}

/** 어느 패턴에서 담은 게 실제로 나았는지 — 이 화면의 존재 이유 */
export interface PatternRoll {
  pattern: string;
  n: number;
  wins: number;
  avgPct: number;
  totalPnl: number;
}

export function byPattern(rows: Valued[]): PatternRoll[] {
  const g = new Map<string, Valued[]>();
  for (const r of rows) {
    if (r.pnlPct === null) continue;
    const k = r.pattern ?? "(미지정)";
    (g.get(k) ?? g.set(k, []).get(k)!).push(r);
  }
  return [...g.entries()]
    .map(([pattern, rs]) => ({
      pattern,
      n: rs.length,
      wins: rs.filter((r) => r.pnlPct! > 0).length,
      avgPct: rs.reduce((s, r) => s + r.pnlPct!, 0) / rs.length,
      totalPnl: rs.reduce((s, r) => s + (r.pnlAmount ?? 0), 0),
    }))
    .sort((a, b) => b.avgPct - a.avgPct);
}

export function add(
  list: Position[],
  input: {
    market: MarketKey; ticker: string; name: string;
    entryDate: string; entryPrice: number; shares: number;
    pattern?: PatternKey | null; note?: string;
  }
): Position[] {
  return [
    ...list,
    { id: newId(), exitDate: null, exitPrice: null, ...input },
  ];
}

export function remove(list: Position[], id: string): Position[] {
  return list.filter((p) => p.id !== id);
}

export function close(
  list: Position[], id: string, exitDate: string, exitPrice: number
): Position[] {
  return list.map((p) => (p.id === id ? { ...p, exitDate, exitPrice } : p));
}

export function reopen(list: Position[], id: string): Position[] {
  return list.map((p) => (p.id === id ? { ...p, exitDate: null, exitPrice: null } : p));
}

/** 브라우저를 옮길 때 쓰는 백업. localStorage가 유일한 저장소라 이게 없으면 기록이 갇힌다. */
export function toJSON(list: Position[]): string {
  return JSON.stringify(list, null, 2);
}

export function fromJSON(text: string): Position[] | null {
  try {
    const parsed: unknown = JSON.parse(text);
    if (!Array.isArray(parsed)) return null;
    const rows = parsed.filter(isPosition);
    return rows.length ? rows : null;
  } catch {
    return null;
  }
}
