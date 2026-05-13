"use client";
import useSWR from "swr";
import { motion } from "framer-motion";
import { TrendingUp, Activity, RefreshCw, BarChart2, Star, Zap, Layers, Eye, Box, Trophy } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { StockTable } from "@/components/StockTable";
import { fetchLatestResult } from "@/lib/fetcher";
import type { PatternKey } from "@/lib/types";

const PATTERNS: { key: PatternKey; label: string; desc: string; icon: React.ElementType; color: string; bg: string }[] = [
  { key: "common",  label: "★ 공통 추출",      desc: "3개 이상 패턴에서 동시 추출된 최우선 종목",            icon: Trophy,    color: "text-yellow-400", bg: "bg-yellow-500/10" },
  { key: "p1",      label: "정배열 + 매집",    desc: "이평선 정배열 퍼지기 직전 + OBV 매집 신호",           icon: TrendingUp, color: "text-indigo-400", bg: "bg-indigo-500/10" },
  { key: "p2",      label: "5일선 추세",       desc: "5일선 지지 + 정배열 완성 + 거래량 터짐",              icon: Activity,  color: "text-emerald-400", bg: "bg-emerald-500/10" },
  { key: "p3",      label: "눌림목",           desc: "피보나치 되돌림 구간 + MACD 반등",                    icon: BarChart2, color: "text-amber-400",   bg: "bg-amber-500/10" },
  { key: "canslim", label: "CAN SLIM",         desc: "O'Neil — 52주 신고가 + 거래량 폭발 + 상대강도",       icon: Star,      color: "text-blue-400",    bg: "bg-blue-500/10" },
  { key: "vcp",     label: "VCP",              desc: "Minervini — 변동성 수축 후 돌파 직전",                icon: Zap,       color: "text-purple-400",  bg: "bg-purple-500/10" },
  { key: "stage2",  label: "Stage 2",          desc: "Weinstein — MA120 위 + 우상향 안정 추세",             icon: Layers,    color: "text-cyan-400",    bg: "bg-cyan-500/10" },
  { key: "wyckoff", label: "Wyckoff",          desc: "Wyckoff — OBV 신고점 스마트머니 매집",                icon: Eye,       color: "text-rose-400",    bg: "bg-rose-500/10" },
  { key: "darvas",  label: "Darvas Box",       desc: "Darvas — 52주 신고가 박스권 돌파 + 거래량 폭발",      icon: Box,       color: "text-orange-400",  bg: "bg-orange-500/10" },
];

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white/5 border border-white/10 rounded-xl px-5 py-4 flex flex-col gap-1"
    >
      <span className="text-xs text-white/40 uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold font-mono ${color}`}>{value}</span>
      <span className="text-xs text-white/30">종목</span>
    </motion.div>
  );
}

export default function Home() {
  const { data, isLoading, mutate } = useSWR("screener", fetchLatestResult, {
    refreshInterval: 1000 * 60 * 5,
  });

  const runAt = data?.run_at
    ? new Date(data.run_at.seconds * 1000).toLocaleString("ko-KR")
    : null;

  return (
    <main className="min-h-screen bg-[#080a0f] text-white">
      <header className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-xs font-bold">Q</div>
          <span className="font-semibold tracking-tight">QuantTrading</span>
          <span className="text-xs text-white/30 px-2 py-0.5 bg-white/5 rounded">KOSPI · KOSDAQ</span>
        </div>
        <div className="flex items-center gap-3 text-xs text-white/40">
          {runAt && <span>마지막 업데이트: {runAt}</span>}
          <button onClick={() => mutate()} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors">
            <RefreshCw size={13} />
          </button>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {isLoading ? (
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 bg-white/5 rounded-xl" />)}
          </div>
        ) : data ? (
          <div className="grid grid-cols-5 gap-3">
            <StatCard label="★ 공통 추출"   value={data.common_count}  color="text-yellow-400" />
            <StatCard label="CAN SLIM"      value={data.canslim_count} color="text-blue-400" />
            <StatCard label="VCP"           value={data.vcp_count}     color="text-purple-400" />
            <StatCard label="Stage 2"       value={data.stage2_count}  color="text-cyan-400" />
            <StatCard label="Wyckoff"       value={data.wyckoff_count} color="text-rose-400" />
          </div>
        ) : null}

        <Tabs defaultValue="common">
          <TabsList className="bg-white/5 border border-white/10 p-1 rounded-xl flex-wrap h-auto gap-1">
            {PATTERNS.map((p) => {
              const Icon = p.icon;
              return (
                <TabsTrigger
                  key={p.key}
                  value={p.key}
                  className="flex items-center gap-2 data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/50 rounded-lg px-4 py-2 text-sm transition-all"
                >
                  <Icon size={14} className={p.color} />
                  {p.label}
                </TabsTrigger>
              );
            })}
          </TabsList>

          {PATTERNS.map((p) => (
            <TabsContent key={p.key} value={p.key} className="mt-4">
              <div className={`mb-4 px-4 py-3 rounded-xl ${p.bg} border border-white/5`}>
                <p className="text-sm text-white/60">{p.desc}</p>
              </div>
              {isLoading ? (
                <div className="space-y-2">
                  {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-14 bg-white/5 rounded-lg" />)}
                </div>
              ) : data ? (
                <StockTable data={data[p.key] ?? []} pattern={p.key} />
              ) : (
                <div className="py-20 text-center text-white/30">데이터가 없습니다</div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>
    </main>
  );
}
