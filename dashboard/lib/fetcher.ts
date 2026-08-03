import { collection, query, orderBy, limit, getDocs, doc, getDoc } from "firebase/firestore";
import { db } from "./firebase";
import type { ScreenerResult, Fundamentals } from "./types";

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

/** 종목별 분기 재무 히스토리. 모달을 열 때만 호출(지연 로딩). */
export async function fetchFundamentals(ticker: string): Promise<Fundamentals | null> {
  const snap = await getDoc(doc(db, "fundamentals", ticker));
  return snap.exists() ? (snap.data() as Fundamentals) : null;
}
