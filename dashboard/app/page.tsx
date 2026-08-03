"use client";
import useSWR from "swr";
import { useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Activity, BarChart2, Star, Zap, Layers, Eye, Box, Trophy, HelpCircle } from "lucide-react";
import { Header } from "@/components/Header";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { StockTable } from "@/components/StockTable";
import { PatternGuideModal } from "@/components/PatternGuideModal";
import { fetchLatestResult } from "@/lib/fetcher";
import type { PatternKey, MarketKey, Stock } from "@/lib/types";

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국",   flag: "🇰🇷" },
  { key: "us",     label: "미국",   flag: "🇺🇸" },
  { key: "crypto", label: "코인",   flag: "₿"   },
];

const PATTERNS: { key: PatternKey; label: string; desc: string; icon: React.ElementType; color: string; bg: string }[] = [
  { key: "common_trend", label: "★ 추세 공통",  desc: "Stage2 + CAN SLIM + Darvas 중 2개+ — 신고가형 상승 추세", icon: Trophy,  color: "text-yellow-400",  bg: "bg-yellow-500/10" },
  { key: "common_accum", label: "★ 매집 공통",  desc: "Wyckoff + VCP 둘 다 해당 — 조정/매집 완료 폭발 직전",  icon: Eye,     color: "text-rose-300",    bg: "bg-rose-500/10" },
  { key: "common_all",   label: "☆ 내 패턴 공통", desc: "정배열매집 + 5일선추세 + 눌림목 중 2개+ — 참고용",  icon: Star,    color: "text-white/50",    bg: "bg-white/5" },
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
  const { data, isLoading } = useSWR("screener", fetchLatestResult, {
    refreshInterval: 1000 * 60 * 5,
  });
  const [market, setMarket] = useState<MarketKey>("kr");
  const [guide, setGuide] = useState<PatternKey | null>(null);

  const runAt = data?.run_at
    ? new Date(data.run_at.seconds * 1000).toLocaleString("ko-KR")
    : null;

  // 현재 선택된 시장의 패턴 데이터 추출
  const getPatternData = (patternKey: PatternKey): Stock[] => {
    const key = `${market}_${patternKey}`;
    return ((data as Record<string, unknown>)?.[key] as Stock[]) ?? [];
  };

  return (
    <main className="min-h-screen bg-[#080a0f] text-white">
      <Header runAt={runAt ?? undefined} />

      <div className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* 마켓 선택 */}
        <div className="flex gap-2">
          {MARKETS.map(({ key, label, flag }) => (
            <button
              key={key}
              onClick={() => setMarket(key)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all border ${
                market === key
                  ? "bg-white/10 border-white/20 text-white"
                  : "bg-transparent border-white/10 text-white/40 hover:text-white/70"
              }`}
            >
              <span>{flag}</span>{label}
            </button>
          ))}
        </div>

        {isLoading ? (
          <div className="grid grid-cols-3 gap-4">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-24 bg-white/5 rounded-xl" />)}
          </div>
        ) : data ? (
          <div className="grid grid-cols-5 gap-3">
            <StatCard label="★ 추세 공통" value={getPatternData("common_trend").length} color="text-yellow-400" />
            <StatCard label="★ 매집 공통" value={getPatternData("common_accum").length} color="text-rose-300" />
            <StatCard label="CAN SLIM"    value={getPatternData("canslim").length}       color="text-blue-400" />
            <StatCard label="VCP"         value={getPatternData("vcp").length}           color="text-purple-400" />
            <StatCard label="Stage 2"     value={getPatternData("stage2").length}        color="text-cyan-400" />
          </div>
        ) : null}

        <Tabs defaultValue="common_trend">
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
              <div className={`mb-4 px-4 py-3 rounded-xl ${p.bg} border border-white/5 flex items-center justify-between gap-3`}>
                <p className="text-sm text-white/60">{p.desc}</p>
                <button
                  onClick={() => setGuide(p.key)}
                  aria-label={`${p.label} 자세한 설명`}
                  className="shrink-0 flex items-center gap-1 text-xs text-white/40 hover:text-white/90 transition-colors"
                >
                  <HelpCircle size={16} />
                  <span className="hidden sm:inline">설명</span>
                </button>
              </div>
              {isLoading ? (
                <div className="space-y-2">
                  {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-14 bg-white/5 rounded-lg" />)}
                </div>
              ) : data ? (
                <StockTable data={getPatternData(p.key)} pattern={p.key} />
              ) : (
                <div className="py-20 text-center text-white/30">데이터가 없습니다</div>
              )}
            </TabsContent>
          ))}
        </Tabs>
      </div>

      <PatternGuideModal pattern={guide} onClose={() => setGuide(null)} />
    </main>
  );
}
