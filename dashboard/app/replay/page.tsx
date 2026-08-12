"use client";
import useSWR from "swr";
import { useState } from "react";
import { motion } from "framer-motion";
import { Header } from "@/components/Header";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchReplay } from "@/lib/fetcher";
import { PATTERN_GUIDE } from "@/lib/patternGuide";
import type { MarketKey, PatternKey, ReplayStat } from "@/lib/types";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국",   flag: "🇰🇷" },
  { key: "us",     label: "미국",   flag: "🇺🇸" },
  { key: "crypto", label: "코인",   flag: "₿"   },
];

const ORDER: PatternKey[] = [
  "common_trend", "common_accum", "common_all",
  "canslim", "vcp", "stage2", "wyckoff", "darvas", "p1", "p2", "p3",
];

function pct(v?: number | null, digits = 2) {
  if (v === undefined || v === null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

function tone(v?: number | null) {
  if (v === undefined || v === null) return "text-white/30";
  return v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-white/50";
}

function Chooser<T extends number>({ label, options, value, onChange, suffix }: {
  label: string; options: T[]; value: T; onChange: (v: T) => void; suffix: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-white/40 uppercase tracking-wider">{label}</span>
      <div className="flex gap-1">
        {options.map((o) => (
          <button
            key={o}
            onClick={() => onChange(o)}
            className={`px-3 py-1.5 rounded-lg text-sm font-mono transition-all border ${
              value === o
                ? "bg-white/10 border-white/20 text-white"
                : "bg-transparent border-white/10 text-white/40 hover:text-white/70"
            }`}
          >
            {o}{suffix}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ReplayPage() {
  const [market, setMarket] = useState<MarketKey>("kr");
  const [hold, setHold] = useState(20);
  const [topK, setTopK] = useState(30);
  const [noStop, setNoStop] = useState(false);

  const { data, isLoading } = useSWR(["replay", market], () => fetchReplay(market));

  const suffix = noStop ? "|nostop" : "";
  const rows = data
    ? ORDER.map((key) => ({ key, stat: data.results[`${key}|${hold}|${topK}${suffix}`] }))
        .filter((r) => r.stat)
        .sort((a, b) => (b.stat!.excess_uni ?? -99) - (a.stat!.excess_uni ?? -99))
    : [];

  const chartData = rows
    .filter((r) => r.stat!.n_dates > 0)
    .map((r) => ({
      name: PATTERN_GUIDE[r.key]?.title.replace(/^[★☆]\s*/, "") ?? r.key,
      excess: (r.stat!.excess_uni ?? 0) * 100,
    }));

  return (
    <div className="min-h-screen bg-[#080a0f] text-white">
      <Header />

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-xl font-bold text-white">과거 재현 — 리스트를 샀으면?</h1>
          <p className="text-sm text-white/40 mt-1">
            매 스캔일마다 유니버스 전체를 스코어링해 상위 N종목을 뽑고, 그 묶음을 동일가중으로
            매수했을 때의 성과. 진입은 신호 다음날 시가, 상장폐지 종목 포함, 거래비용·ATR 손절 반영.
          </p>
          {data && (
            <p className="text-xs text-white/30 mt-1">
              {data.date_from} ~ {data.date_to} · {data.n_tickers.toLocaleString()}종목 ·
              스캔일 {data.n_dates}일 · 패널 {data.panel_rows.toLocaleString()}행 ·
              임계 {data.threshold}점 · 생성 {data.generated_at}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
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
          <Chooser label="보유" options={data?.holds ?? [5, 20, 60]} value={hold} onChange={setHold} suffix="일" />
          <Chooser label="상위" options={data?.tops ?? [10, 20, 30]} value={topK} onChange={setTopK} suffix="종목" />
          <button
            onClick={() => setNoStop(!noStop)}
            className={`px-3 py-1.5 rounded-lg text-sm transition-all border ${
              noStop
                ? "bg-amber-500/15 border-amber-500/30 text-amber-200"
                : "bg-transparent border-white/10 text-white/40 hover:text-white/70"
            }`}
            title="ATR 손절 없이 만기까지 보유했을 때와 비교"
          >
            {noStop ? "손절 미적용" : "손절 적용"}
          </button>
        </div>

        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
          <p className="text-xs text-amber-200/70 leading-relaxed">
            <strong className="text-amber-200">해석 주의.</strong> 보유 {hold}일 구간이 스캔 간격보다 길어
            날짜별 관측이 서로 겹칩니다 — 표시된 스캔일 수만큼 독립 표본이 아니며, 유의성 판단에 쓸 수 없습니다.
            단일 시장·단일 구간 결과이므로 <strong className="text-amber-200">초과수익의 부호와 순위</strong>를
            방향성 참고로만 보세요.
          </p>
        </div>

        {isLoading ? (
          <div className="space-y-4">
            {[...Array(2)].map((_, i) => <Skeleton key={i} className="h-64 bg-white/5 rounded-2xl" />)}
          </div>
        ) : !data ? (
          <div className="py-24 text-center text-white/30">
            이 시장의 재현 데이터가 없습니다.
            <div className="text-xs mt-2 font-mono text-white/20">
              python replay.py build --market {market} &amp;&amp; python replay.py publish --market {market}
            </div>
          </div>
        ) : (
          <>
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-white/60 mb-1 uppercase tracking-wider">
                종목 선정력 — 유니버스 평균 대비
              </h2>
              <p className="text-xs text-white/30 mb-4">
                그날 유동성을 통과한 전 종목을 동일가중으로 산 것보다 나았는지. 지수(시총가중)와
                비교하면 종목 선정이 아니라 가중방식 차이가 섞여 들어간다.
              </p>
              <div className="h-56">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
                    <XAxis dataKey="name" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }}
                      axisLine={false} tickLine={false} interval={0} angle={-20} textAnchor="end" height={56} />
                    <YAxis unit="%" tick={{ fill: "rgba(255,255,255,0.3)", fontSize: 11 }}
                      axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "rgba(255,255,255,0.04)" }}
                      contentStyle={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                      formatter={(v) => [`${Number(v).toFixed(2)}%`, "초과수익"]}
                    />
                    <ReferenceLine y={0} stroke="rgba(255,255,255,0.25)" />
                    <Bar dataKey="excess" radius={[4, 4, 0, 0]}>
                      {chartData.map((d, i) => (
                        <Cell key={i} fill={d.excess >= 0 ? "#34d399" : "#fb7185"} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden"
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-white/40 uppercase tracking-wider border-b border-white/10">
                      <th className="text-left  font-medium px-4 py-3">패턴</th>
                      <th className="text-right font-medium px-3 py-3">리스트</th>
                      <th className="text-right font-medium px-3 py-3">유니버스</th>
                      <th className="text-right font-medium px-3 py-3">선정력</th>
                      <th className="text-right font-medium px-3 py-3">승률</th>
                      <th className="text-right font-medium px-3 py-3">vs 지수</th>
                      <th className="text-right font-medium px-3 py-3">Rank IC</th>
                      <th className="text-right font-medium px-3 py-3">동점</th>
                      <th className="text-right font-medium px-3 py-3">스캔일</th>
                      <th className="text-right font-medium px-3 py-3">평균 종목</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map(({ key, stat }) => (
                      <Row key={key} pkey={key} stat={stat!} />
                    ))}
                  </tbody>
                </table>
              </div>
            </motion.div>

            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <h2 className="text-sm font-medium text-white/60 mb-1 uppercase tracking-wider">
                순위 구간별 초과수익
              </h2>
              <p className="text-xs text-white/30 mb-4">
                상위권이 하위권보다 좋아야 스코어 정렬이 정보를 담고 있다는 뜻. 뒤집혀 있으면
                점수 순서대로 고르는 게 의미가 없다.
              </p>
              <div className="space-y-2">
                {rows.filter(r => r.stat!.rank_buckets && Object.keys(r.stat!.rank_buckets).length > 0)
                  .map(({ key, stat }) => (
                    <div key={key} className="flex items-center gap-3 text-sm">
                      <span className="w-40 shrink-0 text-white/60 text-xs">
                        {PATTERN_GUIDE[key]?.title ?? key}
                      </span>
                      <div className="flex gap-2 flex-wrap">
                        {Object.entries(stat!.rank_buckets!).map(([bucket, v]) => (
                          <span key={bucket}
                            className="px-2.5 py-1 rounded-lg bg-white/5 border border-white/10 text-xs font-mono">
                            <span className="text-white/40">{bucket}</span>
                            <span className={`ml-2 ${tone(v)}`}>{pct(v)}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
              </div>
            </div>

            <p className="text-xs text-white/25 leading-relaxed">
              비용: 수수료 {(data.costs.fee_rate * 100).toFixed(3)}% · 거래세 {(data.costs.tax_rate * 100).toFixed(2)}% ·
              슬리피지 {(data.costs.slippage * 100).toFixed(2)}% (편도 기준). 승률은 유니버스 평균을 이긴 스캔일의
              비율입니다 — 종목 단위로 세면 같은 날의 {topK}종목이 {topK}표가 되어 과대평가됩니다.
              <strong className="text-amber-200/60"> 동점 비율이 높은 패턴</strong>은 상위 N이 전부 같은 점수라
              순위와 Rank IC를 해석하면 안 됩니다 — 어떤 종목이 리스트에 오르는지가 사실상 임의입니다.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function Row({ pkey, stat }: { pkey: PatternKey; stat: ReplayStat }) {
  const guide = PATTERN_GUIDE[pkey];
  const empty = !stat.n_dates;

  return (
    <tr className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
      <td className="px-4 py-3">
        <div className="text-white/90">{guide?.title ?? pkey}</div>
        {guide?.composition && (
          <div className="text-xs text-white/30 mt-0.5">{guide.composition}</div>
        )}
      </td>
      {empty ? (
        <td colSpan={9} className="px-3 py-3 text-right text-xs text-white/25">
          해당 구간에 신호 없음
        </td>
      ) : (
        <>
          <td className={`px-3 py-3 text-right font-mono ${tone(stat.port_return)}`}>{pct(stat.port_return)}</td>
          <td className="px-3 py-3 text-right font-mono text-white/40">{pct(stat.uni_return)}</td>
          <td className={`px-3 py-3 text-right font-mono font-semibold ${tone(stat.excess_uni)}`}>
            {pct(stat.excess_uni)}
          </td>
          <td className={`px-3 py-3 text-right font-mono ${(stat.uni_hit_rate ?? 0) >= 0.5 ? "text-emerald-400" : "text-white/50"}`}>
            {stat.uni_hit_rate === undefined ? "—" : `${(stat.uni_hit_rate * 100).toFixed(0)}%`}
          </td>
          <td className="px-3 py-3 text-right font-mono text-white/30">{pct(stat.excess_return)}</td>
          {/* 동점 비율이 높으면 순위 자체가 임의라 Rank IC를 읽으면 안 된다 */}
          <td className={`px-3 py-3 text-right font-mono ${(stat.tie_ratio ?? 0) > 0.5 ? "text-white/20" : tone(stat.rank_ic)}`}>
            {stat.rank_ic === undefined || stat.rank_ic === null ? "—" : stat.rank_ic.toFixed(3)}
          </td>
          <td className={`px-3 py-3 text-right font-mono ${(stat.tie_ratio ?? 0) > 0.5 ? "text-amber-400" : "text-white/40"}`}>
            {stat.tie_ratio === undefined ? "—" : `${(stat.tie_ratio * 100).toFixed(0)}%`}
          </td>
          <td className="px-3 py-3 text-right font-mono text-white/40">{stat.n_dates}</td>
          <td className="px-3 py-3 text-right font-mono text-white/40">{stat.avg_picks_per_date?.toFixed(1) ?? "—"}</td>
        </>
      )}
    </tr>
  );
}
