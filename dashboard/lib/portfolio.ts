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

export interface Valued extends Position {
  /** 평가에 쓴 현재가. 시세에 없으면 null */
  nowPrice: number | null;
  /** 청산했으면 청산가 기준, 아니면 현재가 기준 */
  pnlPct: number | null;
  pnlAmount: number | null;
  cost: number;
  value: number | null;
  heldDays: number;
  closed: boolean;
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
  return {
    ...p,
    closed,
    nowPrice: mark,
    cost,
    value,
    pnlPct: mark === null || p.entryPrice <= 0 ? null : (mark - p.entryPrice) / p.entryPrice,
    pnlAmount: value === null ? null : value - cost,
    heldDays,
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
  let cost = 0, value = 0, unpriced = 0, wins = 0, losses = 0;
  for (const r of rows) {
    if (r.value === null) { unpriced += 1; continue; }
    cost += r.cost;
    value += r.value;
    if (r.pnlPct !== null && r.pnlPct > 0) wins += 1;
    else if (r.pnlPct !== null && r.pnlPct < 0) losses += 1;
  }
  return {
    cost, value, unpriced, wins, losses,
    pnlAmount: value - cost,
    pnlPct: cost > 0 ? (value - cost) / cost : null,
  };
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
