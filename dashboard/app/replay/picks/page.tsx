"use client";
import useSWR from "swr";
import { useState, useMemo } from "react";
import Link from "next/link";
import { Search, TrendingUp, TrendingDown } from "lucide-react";
import { Header } from "@/components/Header";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchReplayPickIndex, fetchReplayPicks } from "@/lib/fetcher";
import { PATTERN_GUIDE } from "@/lib/patternGuide";
import type { MarketKey, PatternKey, ReplayPick } from "@/lib/types";

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국",   flag: "🇰🇷" },
  { key: "us",     label: "미국",   flag: "🇺🇸" },
  { key: "crypto", label: "코인",   flag: "₿"   },
];

const ORDER: PatternKey[] = [
  "common_trend", "common_accum", "common_all",
  "canslim", "vcp", "stage2", "wyckoff", "darvas", "p1", "p2", "p3",
];

/** now = 안 팔고 현재까지, 나머지는 고정 거래일 보유 후 매도 */
const MODES = [
  { key: "now", label: "안 팔고 지금까지", desc: "그날 사서 오늘까지 들고 있으면" },
  { key: "5",   label: "5일 보유",  desc: "5거래일 뒤 매도 (ATR 손절 적용)" },
  { key: "20",  label: "20일 보유", desc: "20거래일 뒤 매도 (ATR 손절 적용)" },
  { key: "60",  label: "60일 보유", desc: "60거래일 뒤 매도 (ATR 손절 적용)" },
];

function pct(v?: number | null, digits = 2) {
  if (v === undefined || v === null) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

function tone(v?: number | null) {
  if (v === undefined || v === null) return "text-white/30";
  return v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-white/50";
}

function won(v?: number) {
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

export default function PicksPage() {
  const [market, setMarket] = useState<MarketKey>("kr");
  const [pattern, setPattern] = useState<PatternKey>("common_trend");
  const [mode, setMode] = useState("now");
  const [dateIdx, setDateIdx] = useState<number | null>(null);
  const [q, setQ] = useState("");

  const { data: index, isLoading: idxLoading } = useSWR(
    ["pickIndex", market], () => fetchReplayPickIndex(market));

  // 기본값은 20거래일 전에 가장 가까운 날짜 — "20일 전에 샀으면"이 가장 흔한 질문
  const dates = index?.dates ?? [];
  const defaultIdx = useMemo(() => {
    if (!dates.length) return 0;
    let best = 0, gap = Infinity;
    dates.forEach((d, i) => {
      const g = Math.abs(d.bars_ago - 20);
      if (g < gap) { gap = g; best = i; }
    });
    return best;
  }, [dates]);
  const idx = dateIdx ?? defaultIdx;
  const selected = dates[idx];

  const { data: doc, isLoading: docLoading } = useSWR(
    selected ? ["picks", market, selected.date] : null,
    () => fetchReplayPicks(market, selected!.date));

  const block = doc?.patterns?.[pattern];
  const summary = block?.summary?.[mode];
  const retKey = mode === "now" ? "ret_now" : (`ret_${mode}` as keyof ReplayPick);

  const rows = useMemo(() => {
    const all = block?.picks ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return all;
    return all.filter(p =>
      p.name.toLowerCase().includes(needle) || p.ticker.includes(needle));
  }, [block, q]);

  const shown = rows.filter(p => p[retKey] !== null && p[retKey] !== undefined);
  const avg = shown.length
    ? shown.reduce((s, p) => s + (p[retKey] as number), 0) / shown.length
    : null;
  const wins = shown.filter(p => (p[retKey] as number) > 0).length;

  const patternsWithData = ORDER.filter(k => doc?.patterns?.[k]);

  return (
    <div className="min-h-screen bg-[#080a0f] text-white">
      <Header />

      <div className="max-w-6xl mx-auto px-6 py-8 space-y-5">
        <div>
          <h1 className="text-xl font-bold">그날 이 패턴에 있던 종목, 지금 얼마?</h1>
          <p className="text-sm text-white/40 mt-1">
            날짜를 고르면 그날 그 패턴 리스트에 떴던 종목과 각각의 현재 손익을 보여줍니다.
            매수가는 신호 다음날 시가 기준이고, 수수료·거래세·슬리피지가 빠진 실현 수익률입니다.
          </p>
          {index && (
            <p className="text-xs text-white/30 mt-1">
              현재가 기준일 {index.latest_bar} · 상위 {index.top_k}종목 · 임계 {index.threshold}점 ·
              갱신 {index.generated_at} ·{" "}
              <Link href="/replay" className="underline hover:text-white/60">패턴별 집계 보기</Link>
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
          <div className="py-24 text-center text-white/30">
            이 시장의 재현 데이터가 없습니다.
            <div className="text-xs mt-2 font-mono text-white/20">
              python replay.py build --market {market} &amp;&amp; python replay.py publish --market {market}
            </div>
          </div>
        ) : (
          <>
            <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
              <div>
                <label className="text-xs text-white/40 uppercase tracking-wider">진입 날짜</label>
                <div className="flex items-center gap-4 mt-2">
                  <input
                    type="range"
                    min={0}
                    max={dates.length - 1}
                    value={idx}
                    onChange={(e) => setDateIdx(Number(e.target.value))}
                    className="flex-1 accent-indigo-500"
                  />
                  <div className="w-44 shrink-0 text-right">
                    <div className="font-mono text-white">{selected?.date}</div>
                    <div className="text-xs text-white/40">{selected?.bars_ago}거래일 전 진입</div>
                  </div>
                </div>
              </div>

              <div>
                <label className="text-xs text-white/40 uppercase tracking-wider">패턴</label>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {ORDER.map((k) => {
                    const has = patternsWithData.includes(k);
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
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="flex flex-wrap items-end gap-4">
                <div>
                  <label className="text-xs text-white/40 uppercase tracking-wider">보유 방식</label>
                  <div className="flex gap-1.5 mt-2">
                    {MODES.map((m) => (
                      <button
                        key={m.key}
                        onClick={() => setMode(m.key)}
                        title={m.desc}
                        className={`px-3 py-1.5 rounded-lg text-xs transition-all border ${
                          mode === m.key
                            ? "bg-white/10 border-white/25 text-white"
                            : "bg-transparent border-white/10 text-white/40 hover:text-white/70"
                        }`}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex-1 min-w-52">
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
            </div>

            {docLoading ? (
              <Skeleton className="h-96 bg-white/5 rounded-2xl" />
            ) : !block ? (
              <div className="py-20 text-center text-white/30">
                {selected?.date}에는 이 패턴에 뜬 종목이 없습니다. 다른 날짜나 패턴을 골라보세요.
              </div>
            ) : summary?.n === 0 ? (
              <div className="py-20 text-center text-white/30">
                아직 {mode}거래일이 지나지 않았습니다 — 보유 방식을 바꾸거나 더 과거 날짜를 고르세요.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <Stat
                    label={q ? "검색 결과 평균" : "리스트 평균"}
                    value={pct(avg)}
                    sub={`플러스 ${wins}/${shown.length}종목`}
                    color={tone(avg)}
                  />
                  <Stat
                    label="유니버스 평균"
                    value={pct(summary?.uni)}
                    sub="그날 거래 가능 전 종목"
                  />
                  <Stat
                    label="선정력"
                    value={avg !== null && summary?.uni != null ? pct(avg - summary.uni) : "—"}
                    sub="리스트 − 유니버스"
                    color={avg !== null && summary?.uni != null ? tone(avg - summary.uni) : undefined}
                  />
                  <Stat
                    label="지수 대비"
                    value={avg !== null && summary?.bench != null ? pct(avg - summary.bench) : "—"}
                    sub={`벤치마크 ${pct(summary?.bench)}`}
                    color={avg !== null && summary?.bench != null ? tone(avg - summary.bench) : undefined}
                  />
                </div>

                <div className="bg-white/5 border border-white/10 rounded-2xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-xs text-white/40 uppercase tracking-wider border-b border-white/10">
                          <th className="text-left  font-medium px-4 py-3">#</th>
                          <th className="text-left  font-medium px-3 py-3">종목</th>
                          <th className="text-right font-medium px-3 py-3">점수</th>
                          <th className="text-right font-medium px-3 py-3">매수가</th>
                          <th className="text-right font-medium px-3 py-3">
                            {mode === "now" ? "현재가" : "청산가 기준"}
                          </th>
                          <th className="text-right font-medium px-3 py-3">수익률</th>
                          {mode === "now" && <th className="text-right font-medium px-3 py-3">보유일</th>}
                          <th className="text-right font-medium px-3 py-3">
                            {mode === "now" ? "손절선" : "손절청산"}
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((p) => {
                          const r = p[retKey] as number | null | undefined;
                          const pending = r === null || r === undefined;
                          const stopped = mode === "now"
                            ? p.touched_stop
                            : (p[`stop_${mode}` as keyof ReplayPick] as boolean | null);
                          return (
                            <tr key={p.ticker} className="border-b border-white/5 last:border-0 hover:bg-white/[0.02]">
                              <td className="px-4 py-2.5 text-white/30 font-mono text-xs">{p.rank}</td>
                              <td className="px-3 py-2.5">
                                <div className="text-white/90">{p.name}</div>
                                <div className="text-xs text-white/30 font-mono">{p.ticker}</div>
                              </td>
                              <td className="px-3 py-2.5 text-right font-mono text-white/50">{p.score}</td>
                              <td className="px-3 py-2.5 text-right font-mono text-white/60">{won(p.entry)}</td>
                              <td className="px-3 py-2.5 text-right font-mono text-white/60">
                                {mode === "now" ? won(p.last_close) : "—"}
                              </td>
                              <td className={`px-3 py-2.5 text-right font-mono font-semibold ${pending ? "text-white/25" : tone(r)}`}>
                                {pending ? "진행 중" : (
                                  <span className="inline-flex items-center gap-1">
                                    {r! > 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                    {pct(r)}
                                  </span>
                                )}
                              </td>
                              {mode === "now" && (
                                <td className="px-3 py-2.5 text-right font-mono text-white/40">{p.held_bars}</td>
                              )}
                              <td className="px-3 py-2.5 text-right text-xs">
                                {stopped
                                  ? <span className="text-amber-400/80">{mode === "now" ? "터치" : "청산"}</span>
                                  : <span className="text-white/20">—</span>}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  {rows.length === 0 && (
                    <div className="py-12 text-center text-white/30 text-sm">
                      검색 결과가 없습니다.
                    </div>
                  )}
                </div>
              </>
            )}

            <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-4 py-3">
              <p className="text-xs text-amber-200/70 leading-relaxed">
                <strong className="text-amber-200">읽는 법.</strong>{" "}
                <strong>선정력</strong>이 실제로 볼 값입니다 — 그날 거래 가능한 전 종목을 아무거나 샀을 때와
                비교해 이 패턴이 더 나았는지를 봅니다. 지수 대비는 시총가중 지수와 동일가중 리스트를 비교하는
                것이라 종목 선정 실력과 무관한 차이가 섞입니다.
                {" "}
                <strong className="text-amber-200">한 날짜의 결과는 운입니다.</strong>{" "}
                날짜를 여러 개 옮겨보고,{" "}
                <Link href="/replay" className="underline hover:text-amber-100">패턴별 집계</Link>에서
                87개 스캔일 전체 평균을 함께 확인하세요 — 현재 구간(KOSPI +149%) 전체 평균으로는
                유니버스를 뚜렷하게 이기는 패턴이 없습니다.
              </p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
