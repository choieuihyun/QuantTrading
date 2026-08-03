"use client";
import useSWR from "swr";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import { fetchFundamentals } from "@/lib/fetcher";
import type { QuarterRecord } from "@/lib/types";

// dataviz 카테고리 슬롯 1·2 (다크 서피스 #0f1117 검증 통과)
const C_REV = "#3987e5";
const C_INV = "#d95926";

interface Props {
  ticker: string;
}

interface Point {
  label: string;
  매출: number | null;
  재고: number | null;
  burden: number | null;
}

/** 재고 사이클 판정 — 재고와 매출이 서로 반대로 움직일 때 신호가 가장 강하다. */
function verdict(invYoy: number | null, revYoy: number | null) {
  if (invYoy === null || revYoy === null) return null;
  if (invYoy < 0 && revYoy > 0)
    return { text: "업황 개선 신호 — 재고 감소 + 매출 증가", tone: "good" as const };
  if (invYoy > 0 && revYoy > 0)
    return { text: "확장 국면 — 수요 대응 증산", tone: "neutral" as const };
  if (invYoy > 0 && revYoy <= 0)
    return { text: "재고 부담 — 매출 둔화에도 재고 증가", tone: "bad" as const };
  return { text: "조정 국면 — 감산으로 재고 정리 중", tone: "neutral" as const };
}

function toJo(v: number | null | undefined): number | null {
  return v === null || v === undefined ? null : Number((v / 1e12).toFixed(2));
}

export function InventoryCycleChart({ ticker }: Props) {
  const { data, isLoading, error } = useSWR(["fundamentals", ticker], () =>
    fetchFundamentals(ticker),
  );

  if (isLoading)
    return <div className="h-40 flex items-center justify-center text-xs text-white/30">재무 히스토리 불러오는 중…</div>;

  if (error)
    return (
      <div className="h-20 flex items-center justify-center text-xs text-amber-400/70">
        재무 히스토리를 읽지 못했습니다 (Firestore 규칙에서 fundamentals 읽기 허용 필요)
      </div>
    );

  const quarters = data?.quarters;
  if (!quarters || Object.keys(quarters).length === 0)
    return <div className="h-20 flex items-center justify-center text-xs text-white/30">분기 재무 데이터가 아직 없습니다</div>;

  const sorted = Object.entries(quarters)
    .map(([key, q]) => ({ key, ...(q as QuarterRecord) }))
    .sort((a, b) => a.y - b.y || a.q - b.q);

  const points: Point[] = sorted.map((q) => ({
    label: `${String(q.y).slice(2)}Q${q.q}`,
    매출: toJo(q.rev),
    재고: toJo(q.inventory),
    burden: q.rev && q.inventory ? Number((q.inventory / q.rev).toFixed(2)) : null,
  }));

  const last = sorted[sorted.length - 1];
  const yearAgo = sorted.find((q) => q.y === last.y - 1 && q.q === last.q);
  const pct = (now?: number | null, before?: number | null) =>
    now != null && before != null && before !== 0 ? (now - before) / Math.abs(before) : null;
  const invYoy = pct(last?.inventory, yearAgo?.inventory);
  const revYoy = pct(last?.rev, yearAgo?.rev);
  const v = verdict(invYoy, revYoy);
  const burden = points[points.length - 1]?.burden;

  const toneClass =
    v?.tone === "good"
      ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
      : v?.tone === "bad"
      ? "bg-rose-500/10 text-rose-300 border-rose-500/20"
      : "bg-white/5 text-white/60 border-white/10";

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <p className="text-xs text-white/40">재고 사이클 · 분기 추이 (조원)</p>
        {burden != null && (
          <span className="text-[11px] text-white/40">
            재고부담(재고÷매출) <span className="font-mono text-white/70">{burden}</span>
          </span>
        )}
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 4, right: 8, bottom: 0, left: -18 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: "rgba(255,255,255,0.4)", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "#1a1d27",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 8,
                fontSize: 12,
              }}
              labelStyle={{ color: "rgba(255,255,255,0.6)" }}
              formatter={(val, name) => [`${val}조`, String(name)]}
              cursor={{ stroke: "rgba(255,255,255,0.2)" }}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, color: "rgba(255,255,255,0.5)" }}
              iconType="plainline"
            />
            <Line type="monotone" dataKey="매출" stroke={C_REV} strokeWidth={2} dot={{ r: 3 }} connectNulls />
            <Line type="monotone" dataKey="재고" stroke={C_INV} strokeWidth={2} dot={{ r: 3 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {v && (
        <div className={`text-xs px-3 py-2 rounded-lg border ${toneClass}`}>
          {v.text}
          <span className="ml-2 opacity-70 font-mono">
            재고 YoY {invYoy != null ? `${(invYoy * 100).toFixed(1)}%` : "-"} · 매출 YoY{" "}
            {revYoy != null ? `${(revYoy * 100).toFixed(1)}%` : "-"}
          </span>
        </div>
      )}
    </div>
  );
}
