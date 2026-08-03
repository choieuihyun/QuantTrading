"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  flexRender, type ColumnDef, type SortingState,
} from "@tanstack/react-table";
import { ChevronUp, ChevronDown } from "lucide-react";
import { ScoreBar } from "./ScoreBar";
import { StockDetailModal } from "./StockDetailModal";
import type { Stock } from "@/lib/types";

import type { PatternKey } from "@/lib/types";

interface Props {
  data: Stock[];
  pattern: PatternKey;
  universe?: Stock[]; // 동종업계 비교용 — 전 패턴 종목 합집합
}

const PATTERN_COLS: Record<string, (keyof Stock)[]> = {
  p1:      ["bb_squeeze", "obv_rising", "bullish_ratio"],
  p2:      ["full_aligned", "no_ma5_break"],
  p3:      ["pullback_pct", "in_fib_zone", "today_bullish"],
  canslim: ["near_52w_high", "pos_52w", "rs"],
  vcp:     ["bb_squeeze", "vol_contracting", "pullback_pct"],
  stage2:  ["ma120_rising", "above_ma120_days", "rs"],
  wyckoff: ["obv_new_high", "obv_rising", "bullish_ratio"],
  darvas:  ["pos_52w", "near_52w_high"],
  common_trend: ["pattern_hits", "pos_52w", "rs", "near_52w_high"],
  common_accum: ["pattern_hits", "bb_squeeze", "obv_rising", "vol_contracting"],
  common_all:   ["pattern_hits", "pos_52w", "rs"],
};

const PATTERN_LABELS: Record<string, Record<string, string>> = {
  p1:      { bb_squeeze: "BB수축", obv_rising: "OBV↑", bullish_ratio: "양봉률" },
  p2:      { full_aligned: "정배열", no_ma5_break: "5선유지" },
  p3:      { pullback_pct: "조정폭", in_fib_zone: "피보", today_bullish: "오늘양봉" },
  canslim: { near_52w_high: "신고가근처", pos_52w: "52주위치", rs: "상대강도" },
  vcp:     { bb_squeeze: "BB수축", vol_contracting: "거래량수축", pullback_pct: "조정폭" },
  stage2:  { ma120_rising: "MA120↑", above_ma120_days: "유지일수", rs: "상대강도" },
  wyckoff: { obv_new_high: "OBV신고점", obv_rising: "OBV↑", bullish_ratio: "양봉률" },
  darvas:  { pos_52w: "52주위치", near_52w_high: "신고가근처" },
  common_trend: { pattern_hits: "적중패턴수", pos_52w: "52주위치", rs: "상대강도", near_52w_high: "신고가근처" },
  common_accum: { pattern_hits: "적중패턴수", bb_squeeze: "BB수축", obv_rising: "OBV↑", vol_contracting: "거래량수축" },
  common_all:   { pattern_hits: "적중패턴수", pos_52w: "52주위치", rs: "상대강도" },
};

function formatTradingValue(v: number | undefined, market: string): string {
  if (!v) return "-";
  if (market === "KOSPI" || market === "KOSDAQ") return `${(v / 1e8).toFixed(0)}억`;
  return `$${(v / 1e6).toFixed(1)}M`;
}

function formatExtra(key: string, val: unknown): string {
  if (val === undefined || val === null) return "-";
  if (typeof val === "boolean") return val ? "✓" : "✗";
  if (key === "pullback_pct") return `${((val as number) * 100).toFixed(1)}%`;
  if (key === "bullish_ratio") return `${((val as number) * 100).toFixed(0)}%`;
  return String(val);
}

function ColToggle({ on, onClick, label }: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={on}
      className={`px-2.5 py-1 rounded-lg text-[11px] border transition-colors ${
        on
          ? "bg-white/10 border-white/20 text-white/90"
          : "bg-transparent border-white/10 text-white/40 hover:text-white/70"
      }`}
    >
      {label}
    </button>
  );
}

function FundCell({ value, kind }: { value: number | undefined; kind: "mult" | "pct" }) {
  if (value === undefined || value === null || Number.isNaN(value))
    return <span className="text-white/25">-</span>;
  if (kind === "pct") {
    const pct = value * 100;
    return (
      <span className={`font-mono text-sm ${pct >= 15 ? "text-emerald-400" : pct >= 8 ? "text-white/70" : "text-amber-400"}`}>
        {pct.toFixed(1)}%
      </span>
    );
  }
  // 배수(PER/PBR/PSR): 낮을수록 저평가 → 초록
  const color = value > 0 && value <= 10 ? "text-emerald-400" : value > 25 ? "text-rose-400" : "text-white/70";
  return <span className={`font-mono text-sm ${color}`}>{value.toFixed(1)}</span>;
}

export function StockTable({ data, pattern, universe }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const [selected, setSelected] = useState<Stock | null>(null);
  // 펀더멘털은 기본 노출(리스트에서 바로 봐야 하는 지표), 기술지표는 접어서 폭을 줄인다
  const [showTech, setShowTech] = useState(false);
  const [showFund, setShowFund] = useState(true);

  const extraCols = PATTERN_COLS[pattern];
  const extraLabels = PATTERN_LABELS[pattern];
  const hasFundamentals = data.some((s) => s.per != null || s.roe != null);

  const techCols: ColumnDef<Stock>[] = [
    {
      accessorKey: "rsi",
      header: "RSI",
      cell: ({ getValue }) => {
        const v = getValue() as number;
        const color = v >= 70 ? "text-rose-400" : v >= 50 ? "text-emerald-400" : "text-amber-400";
        return <span className={`font-mono text-sm ${color}`}>{v.toFixed(1)}</span>;
      },
    },
    {
      accessorKey: "vol_ratio",
      header: "거래량",
      cell: ({ getValue }) => {
        const v = getValue() as number;
        return <span className={`font-mono text-sm ${v >= 2 ? "text-emerald-400" : "text-white/60"}`}>{v.toFixed(1)}x</span>;
      },
    },
    {
      accessorKey: "avg_value_20",
      header: "거래대금",
      cell: ({ row }) => (
        <span className="font-mono text-sm text-white/60">
          {formatTradingValue(row.original.avg_value_20, row.original.market)}
        </span>
      ),
    },
  ];

  const fundCols: ColumnDef<Stock>[] = [
    { accessorKey: "per", header: "PER", cell: ({ getValue }) => <FundCell value={getValue() as number} kind="mult" /> },
    { accessorKey: "pbr", header: "PBR", cell: ({ getValue }) => <FundCell value={getValue() as number} kind="mult" /> },
    { accessorKey: "psr", header: "PSR", cell: ({ getValue }) => <FundCell value={getValue() as number} kind="mult" /> },
    { accessorKey: "roe", header: "ROE", cell: ({ getValue }) => <FundCell value={getValue() as number} kind="pct" /> },
    {
      accessorKey: "inventory_yoy",
      header: "재고YoY",
      cell: ({ getValue }) => {
        const v = getValue() as number | undefined;
        if (v == null) return <span className="text-white/25">-</span>;
        // 재고 감소는 업황 개선 신호라 초록
        return (
          <span className={`font-mono text-sm ${v < 0 ? "text-emerald-400" : "text-white/70"}`}>
            {(v * 100).toFixed(1)}%
          </span>
        );
      },
    },
  ];

  const columns: ColumnDef<Stock>[] = [
    {
      accessorKey: "ticker",
      header: "종목",
      cell: ({ row }) => (
        <div>
          <div className="font-semibold text-white">{row.original.name}</div>
          <div className="text-xs text-white/40 font-mono">{row.original.ticker} · {row.original.market}</div>
        </div>
      ),
    },
    {
      accessorKey: "price",
      header: "현재가",
      cell: ({ getValue }) => (
        <span className="font-mono text-white/90">{(getValue() as number).toLocaleString()}</span>
      ),
    },
    {
      accessorKey: "momentum_3m",
      header: "3M",
      cell: ({ getValue }) => {
        const v = getValue() as number;
        const pct = (v * 100).toFixed(1);
        return <span className={`font-mono text-sm ${v > 0 ? "text-emerald-400" : "text-rose-400"}`}>{v > 0 ? "+" : ""}{pct}%</span>;
      },
    },
    ...(showTech ? techCols : []),
    ...(showFund && hasFundamentals ? fundCols : []),
    ...extraCols.map((key) => ({
      accessorKey: key as string,
      header: extraLabels[key as string],
      cell: ({ getValue }: { getValue: () => unknown }) => {
        const val = getValue();
        const text = formatExtra(key as string, val);
        const isGood = val === true || (typeof val === "number" && val > 0.5);
        return <span className={`text-xs font-mono ${isGood ? "text-emerald-400" : "text-white/40"}`}>{text}</span>;
      },
    })),
    {
      accessorKey: "score",
      header: "점수",
      cell: ({ getValue }) => <ScoreBar score={getValue() as number} />,
    },
  ];

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <>
      <div className="flex items-center justify-between mb-2 gap-3">
        <span className="text-xs text-white/30">
          {data.length}종목 · 행을 누르면 상세
        </span>
        <div className="flex items-center gap-1.5">
          <ColToggle on={showTech} onClick={() => setShowTech((v) => !v)} label="기술지표" />
          {hasFundamentals && (
            <ColToggle on={showFund} onClick={() => setShowFund((v) => !v)} label="펀더멘털" />
          )}
        </div>
      </div>

      <div className="rounded-xl border border-white/10 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id} className="border-b border-white/10 bg-white/5">
                {hg.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-4 py-3 text-left text-xs font-medium text-white/50 uppercase tracking-wider cursor-pointer select-none hover:text-white/80 transition-colors"
                    onClick={header.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {header.column.getIsSorted() === "asc" && <ChevronUp size={12} />}
                      {header.column.getIsSorted() === "desc" && <ChevronDown size={12} />}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            <AnimatePresence>
              {table.getRowModel().rows.map((row, i) => (
                <motion.tr
                  key={row.id}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition-colors"
                  onClick={() => setSelected(row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </motion.tr>
              ))}
            </AnimatePresence>
          </tbody>
        </table>
        {data.length === 0 && (
          <div className="py-16 text-center text-white/30 text-sm">조건에 맞는 종목이 없습니다</div>
        )}
      </div>
      <StockDetailModal stock={selected} onClose={() => setSelected(null)} universe={universe} />
    </>
  );
}
