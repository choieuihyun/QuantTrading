"use client";
import useSWR from "swr";
import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Header } from "@/components/Header";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchLatestResult } from "@/lib/fetcher";
import type { MarketKey } from "@/lib/types";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from "recharts";

interface BtStats {
  category: string;
  n_signals?: number;
  n_tickers?: number;
  win_rate_20d?: number;
  avg_return_20d?: number;
  median_return_20d?: number;
  win_rate_60d?: number;
  avg_return_60d?: number;
  n_20d?: number;
  // 손실 거래가 0건이면 정의되지 않아 null로 내려옴
  profit_factor_20d?: number | null;
  payoff_ratio_20d?: number | null;
  stop_hit_rate_20d?: number;
  avg_win_20d?: number;
  avg_loss_20d?: number;
  universe_size?: number;
  sample_size?: number;
  scan_interval?: number;
  costs?: { fee_rate: number; tax_rate: number; slippage: number };
  best_trades?: { ticker: string; entry_date: string; return_20d: number }[];
}

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국",   flag: "🇰🇷" },
  { key: "us",     label: "미국",   flag: "🇺🇸" },
  { key: "crypto", label: "코인",   flag: "₿"   },
];

const CAT_META: Record<string, { label: string; color: string; desc: string }> = {
  common_trend: { label: "돌파 공통",  color: "#facc15", desc: "Stage2 + CAN SLIM + Darvas + VCP 중 2개+" },
  common_accum: { label: "매집 공통",  color: "#fb7185", desc: "Wyckoff 단독" },
  common_all:   { label: "내 패턴 공통", color: "#94a3b8", desc: "P1 + P2 + P3" },
};

function pct(v?: number) {
  if (v === undefined || v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
}

// null = 손실 거래 0건 → 비율이 무한대
function ratio(v: number | null | undefined, hasTrades: boolean) {
  if (v === undefined) return "—";
  if (v === null) return hasTrades ? "∞" : "—";
  return v.toFixed(2);
}

function StatCard({ title, value, sub, color }: { title: string; value: string; sub?: string; color?: string }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs text-white/40 uppercase tracking-wider">{title}</span>
      <span className={`text-2xl font-bold font-mono ${color ?? "text-white"}`}>{value}</span>
      {sub && <span className="text-xs text-white/30">{sub}</span>}
    </div>
  );
}

function CategorySection({ stats }: { stats: BtStats }) {
  const meta = CAT_META[stats.category] ?? { label: stats.category, color: "#fff", desc: "" };

  if (!stats.n_signals) {
    return (
      <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: meta.color }} />
          <h2 className="text-lg font-semibold text-white">{meta.label}</h2>
          <span className="text-xs text-white/40">{meta.desc}</span>
        </div>
        <p className="text-sm text-white/30 mt-3">
          표본 구간에서 신호가 발생하지 않았습니다. 조건이 엄격하거나 해당 시장이 침체 구간이었을 수 있습니다.
        </p>
      </div>
    );
  }

  const hasTrades = (stats.n_20d ?? 0) > 0;
  const pfGood = stats.profit_factor_20d === null
    ? hasTrades
    : (stats.profit_factor_20d ?? 0) >= 1;

  const radarData = [
    { subject: "20일 승률",  value: (stats.win_rate_20d  ?? 0) * 100 },
    { subject: "60일 승률",  value: (stats.win_rate_60d  ?? 0) * 100 },
    { subject: "평균수익",   value: Math.min((stats.avg_return_20d ?? 0) * 500, 100) },
    { subject: "PF",        value: stats.profit_factor_20d === null && hasTrades
                                     ? 100
                                     : Math.min((stats.profit_factor_20d ?? 0) * 40, 100) },
    { subject: "표본 수",    value: Math.min((stats.n_signals ?? 0) / 5, 100) },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-white/5 border border-white/10 rounded-2xl p-6 space-y-5"
    >
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: meta.color }} />
          <h2 className="text-lg font-semibold text-white">{meta.label}</h2>
          <span className="text-xs text-white/40">{meta.desc}</span>
        </div>
        <p className="text-xs text-white/30">
          신호 {stats.n_signals}회 · {stats.n_tickers ?? 0}종목에서 발생
          {stats.scan_interval ? ` · ${stats.scan_interval}거래일 간격 스캔` : ""}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="grid grid-cols-2 gap-3">
          <StatCard title="20일 승률" value={pct(stats.win_rate_20d)}
            color={stats.win_rate_20d && stats.win_rate_20d >= 0.5 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="20일 평균 수익" value={pct(stats.avg_return_20d)}
            sub={`중앙값 ${pct(stats.median_return_20d)}`}
            color={stats.avg_return_20d && stats.avg_return_20d > 0 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="60일 승률" value={pct(stats.win_rate_60d)}
            color={stats.win_rate_60d && stats.win_rate_60d >= 0.5 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="60일 평균 수익" value={pct(stats.avg_return_60d)}
            color={stats.avg_return_60d && stats.avg_return_60d > 0 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="Profit Factor" value={ratio(stats.profit_factor_20d, hasTrades)}
            sub={`손익비 ${ratio(stats.payoff_ratio_20d, hasTrades)}`}
            color={pfGood ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="손절 도달률" value={pct(stats.stop_hit_rate_20d)}
            sub={`평균손실 ${pct(stats.avg_loss_20d)}`} color="text-amber-400" />
        </div>

        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData}>
              <PolarGrid stroke="rgba(255,255,255,0.1)" />
              <PolarAngleAxis dataKey="subject" tick={{ fill: "rgba(255,255,255,0.45)", fontSize: 10 }} />
              <Radar dataKey="value" stroke={meta.color} fill={meta.color} fillOpacity={0.25} />
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {stats.best_trades && stats.best_trades.length > 0 && (
        <div>
          <p className="text-xs text-white/40 mb-2 uppercase tracking-wider">Best Trades (20일 · 비용 반영)</p>
          <div className="flex flex-wrap gap-2">
            {stats.best_trades.map((t, i) => (
              <div key={i} className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg px-3 py-1.5 text-xs">
                <span className="font-mono text-white/70">{t.ticker}</span>
                <span className="text-white/40 mx-1.5">·</span>
                <span className="text-emerald-400 font-semibold">+{(t.return_20d * 100).toFixed(1)}%</span>
                <span className="text-white/30 ml-1.5">{t.entry_date}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

export default function BacktestPage() {
  const { data, isLoading } = useSWR("screener", fetchLatestResult, {
    refreshInterval: 1000 * 60 * 5,
  });
  const [market, setMarket] = useState<MarketKey>("kr");

  const runAt = data?.run_at
    ? new Date(data.run_at.seconds * 1000).toLocaleString("ko-KR")
    : undefined;

  // 업로드 구조가 { kr: {common_trend: ...}, us: {...} } 이므로 시장 단위로 먼저 진입
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const allBt = (data as any)?.backtest as Record<string, Record<string, BtStats>> | undefined;
  const bt = allBt?.[market];

  const anyStats = bt ? Object.values(bt).find(s => s?.sample_size) : undefined;

  const chartData = bt
    ? Object.entries(CAT_META).map(([key, meta]) => ({
        name: meta.label,
        "20일 승률":   ((bt[key]?.win_rate_20d  ?? 0) * 100),
        "60일 승률":   ((bt[key]?.win_rate_60d  ?? 0) * 100),
        "20일 평균수익": ((bt[key]?.avg_return_20d ?? 0) * 100),
      }))
    : [];

  return (
    <div className="min-h-screen bg-[#080a0f] text-white">
      <Header runAt={runAt} />

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-xl font-bold text-white">백테스트 결과</h1>
          <p className="text-sm text-white/40 mt-1">
            유니버스 무작위 표본을 과거 시점부터 슬라이딩 스캔 · 20일/60일 보유 · ATR 손절 및 거래비용 반영
          </p>
          {anyStats && (
            <p className="text-xs text-white/30 mt-1">
              표본 {anyStats.sample_size}종목 / 유니버스 {anyStats.universe_size}종목
              {anyStats.costs && ` · 수수료 ${(anyStats.costs.fee_rate * 100).toFixed(3)}% · 세금 ${(anyStats.costs.tax_rate * 100).toFixed(2)}% · 슬리피지 ${(anyStats.costs.slippage * 100).toFixed(2)}% (편도)`}
            </p>
          )}
        </div>

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

        <div className="bg-indigo-500/5 border border-indigo-500/20 rounded-xl px-4 py-3">
          <p className="text-xs text-indigo-200/70 leading-relaxed">
            <strong className="text-indigo-200">이 페이지는 &quot;신호 단위&quot; 성과입니다.</strong>{" "}
            신호가 뜬 종목을 전부 샀다고 가정하고, 기준선 없이 절대 수익률만 봅니다.
            실제로 화면에 뜬 <strong>상위 N종목 리스트를 샀을 때</strong>가 궁금하다면{" "}
            <Link href="/replay" className="underline hover:text-indigo-100">과거 재현</Link>을 보세요 —
            상장폐지 종목을 포함하고, 유니버스 평균 대비로 종목 선정력을 분리해 측정합니다.
            같은 패턴이라도 두 페이지의 숫자가 다르게 보이는 건 재는 대상이 다르기 때문입니다.
          </p>
        </div>

        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
          <p className="text-xs text-amber-200/70 leading-relaxed">
            <strong className="text-amber-200">해석 주의.</strong> 유니버스는 <em>현재 상장 종목</em> 기준이라
            상장폐지 종목이 빠져 있습니다(생존 편향). 신호가 시간적으로 겹칠 수 있어 실제 독립 표본 수는
            표시된 신호 수보다 적으며, 승률의 신뢰구간은 그만큼 넓습니다. 방향성 참고용으로만 보세요.
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-64 bg-white/5 rounded-2xl" />)}
          </div>
        ) : !bt || Object.keys(bt).length === 0 ? (
          <div className="py-24 text-center text-white/30">
            이 시장의 백테스트 데이터가 없습니다. Actions를 실행해주세요.
          </div>
        ) : (
          <>
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-white/60 mb-4 uppercase tracking-wider">카테고리 비교</h2>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} barGap={4}>
                    <XAxis dataKey="name" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis unit="%" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      formatter={(v) => [`${Number(v).toFixed(1)}%`]}
                    />
                    <Bar dataKey="20일 승률"    fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="60일 승률"    fill="#22d3ee" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="20일 평균수익" fill="#4ade80" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <div className="flex gap-4 mt-2 justify-center">
                {[["#6366f1","20일 승률"],["#22d3ee","60일 승률"],["#4ade80","20일 평균수익"]].map(([c,l])=>(
                  <div key={l} className="flex items-center gap-1.5 text-xs text-white/40">
                    <span className="w-2.5 h-2.5 rounded-sm" style={{ background: c }} />{l}
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              {Object.keys(CAT_META).map(key =>
                bt[key] ? <CategorySection key={key} stats={{ ...bt[key], category: key }} /> : null
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
