"use client";
import useSWR from "swr";
import { useState, useMemo } from "react";
import Link from "next/link";
import { Search, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import { Header } from "@/components/Header";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchScorecardIndex, fetchScorecard } from "@/lib/fetcher";
import { PATTERN_GUIDE } from "@/lib/patternGuide";
import type { MarketKey, PatternKey, ScorePick } from "@/lib/types";

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국",   flag: "🇰🇷" },
  { key: "us",     label: "미국",   flag: "🇺🇸" },
  { key: "crypto", label: "코인",   flag: "₿"   },
];

const ORDER: PatternKey[] = [
  "common_trend", "common_accum", "common_all",
  "canslim", "vcp", "stage2", "wyckoff", "darvas", "p1", "p2", "p3",
];

/** 빠른 이동용 — 정확히 이 일수가 없으면 가장 가까운 진입일로 붙는다 */
const QUICK_DAYS = [5, 10, 20, 30, 60];

function pct(v?: number | null, digits = 2) {
  if (v === undefined || v === null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

function tone(v?: number | null) {
  if (v === undefined || v === null) return "text-white/30";
  return v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-white/50";
}

function num(v?: number | null) {
  if (v === undefined || v === null) return "—";
  return v >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(2);
}

function Stat({ label, value, sub, color }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3">
      <div className="text-xs text-white/40">{label}</div>
      <div className={`text-2xl font-bold font-mono mt-0.5 ${color ?? "text-white"}`}>{value}</div>
      {sub && <div className="text-xs text-white/30 mt-0.5">{sub}</div>}
    </div>
  );
}

export default function TrackPage() {
  const [market, setMarket] = useState<MarketKey>("kr");
  const [pattern, setPattern] = useState<PatternKey>("common_trend");
  const [dateIdx, setDateIdx] = useState<number | null>(null);
  const [q, setQ] = useState("");

  const { data: index, isLoading: idxLoading } = useSWR(
    ["scoreIndex", market], () => fetchScorecardIndex(market),
    { refreshInterval: 1000 * 60 * 10 });

  const dates = index?.dates ?? [];

  /** 원하는 일수에 가장 가까운 진입일 */
  const nearest = useMemo(() => (target: number) => {
    let best = 0, gap = Infinity;
    dates.forEach((d, i) => {
      const g = Math.abs(d.days_ago - target);
      if (g < gap) { gap = g; best = i; }
    });
    return best;
  }, [dates]);

  const idx = dateIdx ?? (dates.length ? nearest(20) : 0);
  const selected = dates[idx];

  const { data: doc, isLoading: docLoading } = useSWR(
    selected ? ["score", market, selected.date] : null,
    () => fetchScorecard(market, selected!.date));

  const block = doc?.patterns?.[pattern];

  const rows = useMemo(() => {
    const all = block?.picks ?? [];
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? all.filter(p => p.name.toLowerCase().includes(needle) || p.ticker.includes(needle))
      : all;
    return [...filtered].sort((a, b) => (b.ret ?? -99) - (a.ret ?? -99));
  }, [block, q]);

  const valid = rows.filter(p => p.ret !== null && p.ret !== undefined);
  const avg = valid.length ? valid.reduce((s, p) => s + p.ret!, 0) / valid.length : null;
  const wins = valid.filter(p => p.ret! > 0).length;
  const available = ORDER.filter(k => doc?.patterns?.[k]);

  return (
    <div className="min-h-screen bg-[#080a0f] text-white">
      <Header />

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-5">
        <div>
          <h1 className="text-xl font-bold">N일 전 이 패턴에 있던 종목, 지금 얼마?</h1>
          <p className="text-sm text-white/40 mt-1">
            과거에 <strong className="text-white/60">실제로 화면에 떴던</strong> 종목 목록과 오늘 가격을
            비교합니다. 과거를 재구성한 게 아니라 저장된 기록이라 편향이 없습니다.
          </p>
          {index && (
            <p className="text-xs text-white/30 mt-1">
              현재가 {index.price_date} 기준 · 갱신 {index.updated_at} (하루 2회 자동) ·{" "}
              <Link href="/replay" className="underline hover:text-white/60">3년치 통계 보기</Link>
            </p>
          )}
        </div>

        <div className="flex gap-2">
          {MARKETS.map(({ key, label, flag }) => (
            <button
              key={key}
              onClick={() => { setMarket(key); setDateIdx(null); }}
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

        {idxLoading ? (
          <Skeleton className="h-72 bg-white/5 rounded-2xl" />
        ) : !index || !dates.length ? (
          <div className="py-20 text-center">
            <div className="text-white/40">아직 성적표가 없습니다.</div>
            <div className="text-xs text-white/25 mt-2 max-w-md mx-auto leading-relaxed">
              과거 스크리닝 기록을 모아 계산하므로, 다음 자동 실행(08:30 / 18:00) 이후에 표시됩니다.
            </div>
          </div>
        ) : (
          <>
            <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-white/40 uppercase tracking-wider">진입 시점</label>
                  <div className="flex gap-1">
                    {QUICK_DAYS.map((d) => (
                      <button
                        key={d}
                        onClick={() => setDateIdx(nearest(d))}
                        className="px-2.5 py-1 rounded-md text-xs border border-white/10
                                   text-white/40 hover:text-white/80 hover:border-white/25 transition-colors"
                      >
                        {d}일 전
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min={0}
                    max={dates.length - 1}
                    value={idx}
                    onChange={(e) => setDateIdx(Number(e.target.value))}
                    className="flex-1 accent-indigo-500"
                  />
                  <div className="w-40 shrink-0 text-right">
                    <div className="font-mono text-white">{selected?.date}</div>
                    <div className="text-xs text-white/40">{selected?.days_ago}일 전</div>
                  </div>
                </div>
              </div>

              <div>
                <label className="text-xs text-white/40 uppercase tracking-wider">패턴</label>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ORDER.map((k) => {
                    const has = available.includes(k);
                    return (
                      <button
                        key={k}
                        onClick={() => setPattern(k)}
                        disabled={!has && !docLoading}
                        className={`px-3 py-1.5 rounded-lg text-xs transition-all border ${
                          pattern === k
                            ? "bg-indigo-500/20 border-indigo-500/40 text-white"
                            : has
                              ? "bg-transparent border-white/10 text-white/50 hover:text-white/80"
                              : "bg-transparent border-white/5 text-white/15 cursor-not-allowed"
                        }`}
                      >
                        {PATTERN_GUIDE[k]?.title ?? k}
                        {doc?.patterns?.[k] && (
                          <span className="ml-1.5 text-white/30">{doc.patterns[k].picks.length}</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="max-w-sm">
                <label className="text-xs text-white/40 uppercase tracking-wider">종목 검색</label>
                <div className="relative mt-2">
                  <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
                  <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="종목명 또는 코드"
                    className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-1.5
                               text-sm placeholder:text-white/25 focus:outline-none focus:border-white/25"
                  />
                </div>
              </div>
            </div>

            {docLoading ? (
              <Skeleton className="h-96 bg-white/5 rounded-2xl" />
            ) : !block ? (
              <div className="py-20 text-center text-white/30">
                {selected?.date}에는 이 패턴에 뜬 종목이 없습니다.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Stat
                    label={q ? "검색 결과 평균" : "리스트 평균"}
                    value={pct(avg)}
                    sub={`플러스 ${wins}/${valid.length}종목`}
                    color={tone(avg)}
                  />
                  <Stat label="중앙값" value={pct(block.median)} sub="극단값 영향 제외"
                        color={tone(block.median)} />
                  <Stat label="최고" value={pct(block.best)} color="text-emerald-400" />
                  <Stat label="최저" value={pct(block.worst)} color="text-rose-400" />
                </div>

                {block.gone > 0 && (
                  <div className="flex items-center gap-2 text-xs text-amber-200/70 px-1">
                    <AlertTriangle size={13} />
                    {block.gone}종목은 오늘 유니버스에 없습니다 (상장폐지·거래정지·유동성 미달) —
                    평균 계산에서 제외됐습니다.
                  </div>
                )}

                <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-white/40 uppercase tracking-wider border-b border-white/10">
                          <th className="text-left  font-medium px-4 py-3">종목</th>
                          <th className="text-right font-medium px-3 py-3">점수</th>
                          <th className="text-right font-medium px-3 py-3">그날 가격</th>
                          <th className="text-right font-medium px-3 py-3">현재가</th>
                          <th className="text-right font-medium px-3 py-3">수익률</th>
                          <th className="text-right font-medium px-3 py-3">손절선</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((p: ScorePick) => (
                          <tr key={p.ticker} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                            <td className="px-4 py-2.5">
                              <div className="text-white/90">{p.name}</div>
                              <div className="text-xs text-white/30 font-mono">{p.ticker}</div>
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono text-white/50">
                              {p.score ?? "—"}
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono text-white/60">{num(p.entry)}</td>
                            <td className="px-3 py-2.5 text-right font-mono text-white/60">
                              {p.gone
                                ? <span className="text-amber-400/60 text-xs">거래없음</span>
                                : num(p.now)}
                            </td>
                            <td className={`px-3 py-2.5 text-right font-mono font-semibold ${tone(p.ret)}`}>
                              {p.ret === null || p.ret === undefined ? "—" : (
                                <span className="inline-flex items-center gap-1">
                                  {p.ret > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                  {pct(p.ret)}
                                </span>
                              )}
                            </td>
                            <td className="px-3 py-2.5 text-right font-mono text-xs text-white/30">
                              {num(p.stop_swing)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {rows.length === 0 && (
                    <div className="py-12 text-center text-white/30 text-sm">검색 결과가 없습니다.</div>
                  )}
                </div>
              </>
            )}

            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
              <p className="text-xs text-amber-200/70 leading-relaxed">
                <strong className="text-amber-200">읽는 법.</strong>{" "}
                &ldquo;그날 가격&rdquo;은 화면에 표시됐던 종가입니다. 실제로는 다음날 시가에 샀을 테니
                체결가는 조금 달랐을 겁니다. 수수료·세금은 빠지지 않은 단순 등락률입니다.{" "}
                <strong className="text-amber-200">한 날짜의 결과는 운입니다</strong> — 날짜를 여러 개
                옮겨보고, 이 리스트가 시장 전체보다 나았는지는{" "}
                <Link href="/replay" className="underline hover:text-amber-100">3년치 통계</Link>에서
                확인하세요.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
