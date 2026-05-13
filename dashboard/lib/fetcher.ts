import { collection, query, orderBy, limit, getDocs } from "firebase/firestore";
import { db } from "./firebase";
import type { ScreenerResult } from "./types";

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
