import { collection, query, orderBy, limit, getDocs, doc, getDoc } from "firebase/firestore";
import { db } from "./firebase";
import type {
  ScreenerResult, Fundamentals, ReplayGrid, MarketKey,
  ReplayPickDoc, ReplayPickIndex,
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
