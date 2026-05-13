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

interface Props {
  data: Stock[];
  pattern: "p1" | "p2" | "p3";
}

const PATTERN_COLS: Record<string, (keyof Stock)[]> = {
  p1: ["bb_squeeze", "obv_rising", "bullish_ratio"],
  p2: ["full_aligned", "no_ma5_break"],
  p3: ["pullback_pct", "in_fib_zone", "today_bullish"],
};

const PATTERN_LABELS: Record<string, Record<string, string>> = {
  p1: { bb_squeeze: "BB수축", obv_rising: "OBV↑", bullish_ratio: "양봉률" },
  p2: { full_aligned: "정배열", no_ma5_break: "5선유지" },
  p3: { pullback_pct: "조정폭", in_fib_zone: "피보", today_bullish: "오늘양봉" },
};

function formatExtra(key: string, val: unknown): string {
  if (val === undefined || val === null) return "-";
  if (typeof val === "boolean") return val ? "✓" : "✗";
  if (key === "pullback_pct") return `${((val as number) * 100).toFixed(1)}%`;
  if (key === "bullish_ratio") return `${((val as number) * 100).toFixed(0)}%`;
  return String(val);
}

export function StockTable({ data, pattern }: Props) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);
  const [selected, setSelected] = useState<Stock | null>(null);

  const extraCols = PATTERN_COLS[pattern];
  const extraLabels = PATTERN_LABELS[pattern];

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
      accessorKey: "momentum_3m",
      header: "3M",
      cell: ({ getValue }) => {
        const v = getValue() as number;
        const pct = (v * 100).toFixed(1);
        return <span className={`font-mono text-sm ${v > 0 ? "text-emerald-400" : "text-rose-400"}`}>{v > 0 ? "+" : ""}{pct}%</span>;
      },
    },
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
      <div className="rounded-xl border border-white/10 overflow-hidden">
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
      <StockDetailModal stock={selected} onClose={() => setSelected(null)} />
    </>
  );
}
