import { collection, query, orderBy, limit, getDocs, doc, getDoc } from "firebase/firestore";
import { db } from "./firebase";
import type {
  ScreenerResult, Fundamentals, ReplayGrid, MarketKey,
  ReplayPickDoc, ReplayPickIndex, ScorecardDoc, ScorecardIndex, PriceDoc,
  SignalIndex, SignalShard, SignalRow, FlowDoc, FlowRow, DisclosureDoc, DisclosureRow,
  WatchDoc, WatchRow,
} from "./types";

export async function fetchLatestResult(): Promise<ScreenerResult | null> {
  const q = query(
    collection(db, "screener_results"),
    orderBy("run_at", "desc"),
    limit(1)
  );
  const snap = await getDocs(q);
  if (snap.empty) return null;
  return snap.docs[0].data() as ScreenerResult;
}

/** 과거 재현 결과. 보유일·상위N 조합이 미리 계산돼 있어 문서 하나만 받으면 된다. */
export async function fetchReplay(market: MarketKey): Promise<ReplayGrid | null> {
  const snap = await getDoc(doc(db, "replay_results", market));
  return snap.exists() ? (snap.data() as ReplayGrid) : null;
}

/** 실전 성적표 — 선택 가능한 진입일 목록. 하루 2회 자동 갱신된다. */
export async function fetchScorecardIndex(market: MarketKey): Promise<ScorecardIndex | null> {
  const snap = await getDoc(doc(db, "scorecard", `${market}_index`));
  return snap.exists() ? (snap.data() as ScorecardIndex) : null;
}

/**
 * 종목 하나를 전 기간·전 패턴에서 추적.
 * 날짜별로 문서가 쪼개져 있어 전부 읽어야 한다 — 40일치라 한 번에 받아도 부담 없다.
 */
export async function fetchTickerHistory(
  market: MarketKey,
  dates: string[]
): Promise<ScorecardDoc[]> {
  const docs = await Promise.all(
    dates.map((d) => getDoc(doc(db, "scorecard", `${market}_${d}`)))
  );
  return docs.filter((s) => s.exists()).map((s) => s.data() as ScorecardDoc);
}

/** 특정 진입일의 패턴별 종목 성적. 날짜당 문서가 나뉘어 있다. */
export async function fetchScorecard(
  market: MarketKey,
  date: string
): Promise<ScorecardDoc | null> {
  const snap = await getDoc(doc(db, "scorecard", `${market}_${date}`));
  return snap.exists() ? (snap.data() as ScorecardDoc) : null;
}

/** 선택 가능한 날짜 목록. 화면 진입 시 한 번만 읽는다. */
export async function fetchReplayPickIndex(market: MarketKey): Promise<ReplayPickIndex | null> {
  const snap = await getDoc(doc(db, "replay_picks", `${market}_index`));
  return snap.exists() ? (snap.data() as ReplayPickIndex) : null;
}

/** 특정 날짜의 종목별 내역. 날짜당 문서가 나뉘어 있어 고른 날짜 하나만 받는다. */
export async function fetchReplayPicks(
  market: MarketKey,
  date: string
): Promise<ReplayPickDoc | null> {
  const snap = await getDoc(doc(db, "replay_picks", `${market}_${date}`));
  return snap.exists() ? (snap.data() as ReplayPickDoc) : null;
}

/** 종목별 분기 재무 히스토리. 모달을 열 때만 호출(지연 로딩). */
export async function fetchFundamentals(ticker: string): Promise<Fundamentals | null> {
  const snap = await getDoc(doc(db, "fundamentals", ticker));
  return snap.exists() ? (snap.data() as Fundamentals) : null;
}

/** 유니버스 전 종목 시세. 가상 매매 평가에 쓴다 — 보유 종목이 패턴 목록에 없어도 값이 나온다. */
export async function fetchPrices(market: MarketKey): Promise<PriceDoc | null> {
  const snap = await getDoc(doc(db, "prices", market));
  return snap.exists() ? (snap.data() as PriceDoc) : null;
}

/**
 * 종목 조회용 샤드 키. screener/explain.py의 shard_of와 반드시 같은 식이어야 한다.
 * 한국 종목코드는 끝자리가 전부 0이라 마지막 글자로 나누면 한 샤드에 전부 몰린다.
 */
export function shardOf(ticker: string, shards: number): number {
  let sum = 0;
  for (const ch of ticker) sum += ch.codePointAt(0)!;
  return sum % shards;
}

export async function fetchSignalIndex(market: MarketKey): Promise<SignalIndex | null> {
  const snap = await getDoc(doc(db, "signals", `${market}_index`));
  return snap.exists() ? (snap.data() as SignalIndex) : null;
}

/** 검색한 종목이 속한 샤드 하나만 읽는다 — 전 종목은 한 문서에 안 들어간다. */
export async function fetchSignalShard(
  market: MarketKey,
  shard: number
): Promise<(SignalShard & { tickers: Record<string, SignalRow> }) | null> {
  const snap = await getDoc(doc(db, "signals", `${market}_${shard}`));
  if (!snap.exists()) return null;
  const d = snap.data() as SignalShard;
  return { ...d, tickers: unpack<SignalRow>(d.tickers_json, d.tickers) };
}

/**
 * 종목별 데이터는 JSON 문자열 한 덩어리로 저장돼 있다 — 맵으로 두면 Firestore가
 * 필드마다 색인을 만들어 문서당 4만 개 한도를 넘긴다. 여기서 한 번만 파싱한다.
 */
function unpack<T>(
  raw: string | undefined,
  legacy?: Record<string, T>
): Record<string, T> {
  // JSON 문자열 전환 이전 실행이 남긴 문서는 맵을 그대로 갖고 있다.
  // 다음 스크리너 실행 전까지 화면이 빈 상태가 되지 않도록 둘 다 받는다.
  if (!raw) return legacy ?? {};
  try {
    return JSON.parse(raw) as Record<string, T>;
  } catch {
    return legacy ?? {};
  }
}

/** KRX 수급·공매도. 로컬 보강 실행에서만 채워지므로 없을 수 있다. */
export async function fetchFlows(
  market: MarketKey
): Promise<(FlowDoc & { tickers: Record<string, FlowRow> }) | null> {
  const snap = await getDoc(doc(db, "flows", market));
  if (!snap.exists()) return null;
  const d = snap.data() as FlowDoc;
  return { ...d, tickers: unpack<FlowRow>(d.tickers_json, d.tickers) };
}

/** DART 공시. 패턴 목록에 오른 종목만 수집된다. */
export async function fetchDisclosures(
  market: MarketKey
): Promise<(DisclosureDoc & { tickers: Record<string, DisclosureRow> }) | null> {
  const snap = await getDoc(doc(db, "disclosures", market));
  if (!snap.exists()) return null;
  const d = snap.data() as DisclosureDoc;
  return { ...d, tickers: unpack<DisclosureRow>(d.tickers_json, d.tickers) };
}

/** 돌파 대기 — 발동가까지 가까운 순. 하루 3번 갱신된다. */
export async function fetchWatchlist(market: MarketKey): Promise<WatchDoc | null> {
  const snap = await getDoc(doc(db, "watchlist", market));
  if (!snap.exists()) return null;
  const d = snap.data() as WatchDoc;
  // 이쪽만 배열이라 unpack(맵 전용)을 쓰지 않는다
  let rows: WatchRow[] = d.rows ?? [];
  if (d.rows_json) {
    try { rows = JSON.parse(d.rows_json) as WatchRow[]; } catch { /* 구버전 문서 */ }
  }
  return { ...d, rows };
}
