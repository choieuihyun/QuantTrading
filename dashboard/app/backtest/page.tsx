"use client";
import useSWR from "swr";
import { motion } from "framer-motion";
import { Header } from "@/components/Header";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchLatestResult } from "@/lib/fetcher";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
} from "recharts";

interface BtStats {
  category: string;
  n_signals?: number;
  win_rate_20d?: number;
  avg_return_20d?: number;
  win_rate_60d?: number;
  avg_return_60d?: number;
  profit_factor_20d?: number;
  avg_win_20d?: number;
  avg_loss_20d?: number;
  best_trades?: { ticker: string; entry_date: string; return_20d: number }[];
}

const CAT_META: Record<string, { label: string; color: string; desc: string }> = {
  common_trend: { label: "추세 공통",  color: "#facc15", desc: "Stage2 + CAN SLIM + Darvas" },
  common_accum: { label: "매집 공통",  color: "#fb7185", desc: "Wyckoff + VCP" },
  common_all:   { label: "내 패턴 공통", color: "#94a3b8", desc: "P1 + P2 + P3" },
};

function pct(v?: number) {
  if (v === undefined || v === null) return "—";
  return `${(v * 100).toFixed(1)}%`;
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

  const radarData = [
    { subject: "20일 승률",  value: (stats.win_rate_20d  ?? 0) * 100 },
    { subject: "60일 승률",  value: (stats.win_rate_60d  ?? 0) * 100 },
    { subject: "평균수익",   value: Math.min((stats.avg_return_20d ?? 0) * 500, 100) },
    { subject: "손익비",     value: Math.min((stats.profit_factor_20d ?? 0) * 25, 100) },
    { subject: "신호 수",    value: Math.min((stats.n_signals ?? 0) * 2, 100) },
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
        <p className="text-xs text-white/30">신호 발생 횟수: {stats.n_signals ?? 0}회</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* 통계 카드 */}
        <div className="grid grid-cols-2 gap-3">
          <StatCard title="20일 승률" value={pct(stats.win_rate_20d)}
            color={stats.win_rate_20d && stats.win_rate_20d >= 0.5 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="20일 평균 수익" value={pct(stats.avg_return_20d)}
            color={stats.avg_return_20d && stats.avg_return_20d > 0 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="60일 승률" value={pct(stats.win_rate_60d)}
            color={stats.win_rate_60d && stats.win_rate_60d >= 0.5 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="60일 평균 수익" value={pct(stats.avg_return_60d)}
            color={stats.avg_return_60d && stats.avg_return_60d > 0 ? "text-emerald-400" : "text-rose-400"} />
          <StatCard title="평균 수익 거래" value={pct(stats.avg_win_20d)} color="text-emerald-400" />
          <StatCard title="평균 손실 거래" value={pct(stats.avg_loss_20d)} color="text-rose-400"
            sub={`손익비: ${stats.profit_factor_20d?.toFixed(2) ?? "—"}`} />
        </div>

        {/* 레이더 차트 */}
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

      {/* 베스트 트레이드 */}
      {stats.best_trades && stats.best_trades.length > 0 && (
        <div>
          <p className="text-xs text-white/40 mb-2 uppercase tracking-wider">Best Trades (20일)</p>
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

  const runAt = data?.run_at
    ? new Date(data.run_at.seconds * 1000).toLocaleString("ko-KR")
    : undefined;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const bt = (data as any)?.backtest as Record<string, BtStats> | undefined;

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
            270일 히스토리 슬라이딩 윈도우 · 매주 신호 체크 · 20일/60일 수익률 측정
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => <Skeleton key={i} className="h-64 bg-white/5 rounded-2xl" />)}
          </div>
        ) : !bt ? (
          <div className="py-24 text-center text-white/30">
            백테스트 데이터가 없습니다. Actions를 실행해주세요.
          </div>
        ) : (
          <>
            {/* 비교 바 차트 */}
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-white/60 mb-4 uppercase tracking-wider">카테고리 비교</h2>
              <div className="h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} barGap={4}>
                    <XAxis dataKey="name" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis unit="%" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      contentStyle={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      formatter={(v: number) => [`${v.toFixed(1)}%`]}
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

            {/* 카테고리별 상세 */}
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
