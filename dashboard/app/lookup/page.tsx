"use client";
import useSWR from "swr";
import { useMemo, useState } from "react";
import { Search, CircleCheck, CircleX, MinusCircle, AlertCircle } from "lucide-react";
import { Header } from "@/components/Header";
import { DataError } from "@/components/DataError";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchPrices, fetchSignalIndex, fetchSignalShard, shardOf } from "@/lib/fetcher";
import { PATTERN_GUIDE } from "@/lib/patternGuide";
import { SupplyPanel } from "@/components/SupplyPanel";
import type { MarketKey, PatternKey, SignalEntry, SignalState } from "@/lib/types";

const MARKETS: { key: MarketKey; label: string; flag: string }[] = [
  { key: "kr",     label: "한국", flag: "🇰🇷" },
  { key: "us",     label: "미국", flag: "🇺🇸" },
  { key: "crypto", label: "코인", flag: "₿"  },
];

const ORDER: PatternKey[] = [
  "common_trend", "common_accum", "common_all",
  "canslim", "vcp", "stage2", "wyckoff", "darvas", "p1", "p2", "p3",
];

const LABEL: Record<string, string> = {
  common_trend: "★ 돌파 공통", common_accum: "★ 매집 공통", common_all: "☆ 내 패턴 공통",
  canslim: "CAN SLIM", vcp: "VCP", stage2: "Stage 2", wyckoff: "Wyckoff",
  darvas: "Darvas", p1: "정배열매집", p2: "5일선추세", p3: "눌림목",
};

/**
 * 기준점 대비 위치가 실제로 성과와 관계있는지 — 패턴마다 정반대다.
 * 2026-08-20 실측(63스캔, 보유 20일 초과수익). t가 모두 1.3 미만이라 확정은 아니다.
 * 일괄 "진입점 근접 필터"를 만들면 안 되는 이유가 여기 있다.
 */
const ENTRY_STATS: Partial<Record<PatternKey, string>> = {
  vcp: "실측(20일 초과수익): 기준점 아래 −1.62% / 0~5% +1.57% / 5~20% +0.46% / 20%↑ −0.23%. "
     + "원전 매수구간이 가장 나았지만 t 0.88로 확정은 아닙니다. 통과 건의 절반은 이미 +20%를 넘긴 뒤였습니다.",
  darvas: "실측: 0~5% −1.19% / 5~20% +0.59% / 20%↑ −1.90%. "
        + "원전 매수구간이 오히려 나빴습니다 — 근접도로 판단할 근거가 없습니다.",
  stage2: "실측: 기준점 아래 +1.06% / 0~5% +0.22% / 5~20% +1.28% / 20%↑ +5.55%. "
        + "연장될수록 나았습니다 — 추세추종 성격이라 '늦었다'가 불리하지 않았습니다.",
  wyckoff: "실측: 기준점 아래 −0.46% / 0~5% −0.03% / 5~20% +0.01% / 20%↑ +2.39%. "
         + "매집 패턴이라 71%가 돌파 전에 잡힙니다. 연장 구간이 오히려 나았습니다.",
};

const STATE: Record<SignalState, { text: string; cls: string; Icon: React.ElementType }> = {
  p: { text: "통과",      cls: "text-emerald-400 border-emerald-400/30 bg-emerald-500/10", Icon: CircleCheck },
  l: { text: "점수 미달", cls: "text-amber-300 border-amber-400/30 bg-amber-500/10",       Icon: AlertCircle },
  g: { text: "조건 탈락", cls: "text-white/45 border-white/15 bg-white/5",                 Icon: CircleX },
  x: { text: "대상 제외", cls: "text-white/35 border-white/10 bg-white/[0.03]",            Icon: MinusCircle },
};

export default function LookupPage() {
  const [market, setMarket] = useState<MarketKey>("kr");
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState<string | null>(null);

  const prices = useSWR(["prices", market], () => fetchPrices(market));
  const index = useSWR(["sigidx", market], () => fetchSignalIndex(market));
  const shard = useSWR(
    ticker && index.data ? ["sigshard", market, shardOf(ticker, index.data.shards)] : null,
    ([, m, s]) => fetchSignalShard(m as MarketKey, s as number)
  );

  const names = prices.data?.names ?? {};
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const out: { ticker: string; name: string }[] = [];
    for (const [t, n] of Object.entries(names)) {
      if (t.toLowerCase().includes(s) || n.toLowerCase().includes(s)) {
        out.push({ ticker: t, name: n });
        if (out.length >= 10) break;
      }
    }
    return out;
  }, [q, names]);

  const row = ticker ? shard.data?.tickers?.[ticker] : undefined;
  const err = prices.error ?? index.error ?? shard.error;

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <Header />
      <main className="mx-auto max-w-4xl px-4 py-6 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Search className="w-6 h-6 text-sky-400" /> 종목 조회
            </h1>
            <p className="text-sm text-white/50 mt-1">
              아무 종목이나 검색해 11개 패턴 각각의 점수와 <b className="text-white/70">탈락 사유</b>를 봅니다.
              상위 20위 밖 종목도 조회됩니다.
            </p>
          </div>
          <div className="flex gap-1">
            {MARKETS.map((m) => (
              <button
                key={m.key}
                onClick={() => { setMarket(m.key); setTicker(null); setQ(""); }}
                className={`px-3 py-1.5 rounded-lg text-sm transition ${
                  market === m.key ? "bg-white/15" : "text-white/50 hover:bg-white/5"
                }`}
              >
                {m.flag} {m.label}
              </button>
            ))}
          </div>
        </div>

        {err ? (
          <DataError err={err} collection="signals" />
        ) : prices.isLoading || index.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : !index.data || !prices.data ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">
            이 시장의 판정 데이터가 아직 없습니다. 스크리너를{" "}
            <b className="text-white/70">{market}</b> 시장으로 한 번 돌리면 채워집니다.
          </div>
        ) : (
          <>
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <input
                value={q}
                onChange={(e) => { setQ(e.target.value); setTicker(null); }}
                placeholder="종목명 또는 코드 (예: 삼성전자, 005930)"
                className="w-full rounded-xl bg-white/5 border border-white/10 pl-10 pr-3 py-3
                           outline-none focus:border-sky-400/50"
              />
              {!ticker && matches.length > 0 && (
                <ul className="absolute z-20 mt-1 w-full rounded-xl border border-white/10
                               bg-[#12121a] shadow-2xl overflow-hidden">
                  {matches.map((m) => (
                    <li key={m.ticker}>
                      <button
                        onClick={() => { setTicker(m.ticker); setQ(`${m.name} (${m.ticker})`); }}
                        className="w-full text-left px-4 py-2.5 text-sm hover:bg-white/10 flex justify-between"
                      >
                        <span>{m.name}</span>
                        <span className="text-white/40 tabular-nums">{m.ticker}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <p className="text-xs text-white/40">
              기준일 <b className="text-white/70">{index.data.bar_date}</b> 종가 ·
              판정 대상 {index.data.count.toLocaleString()}종목 · 통과 기준 {index.data.threshold}점
            </p>

            {ticker && shard.isLoading && <Skeleton className="h-64 w-full" />}

            {ticker && !shard.isLoading && !row && (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-5 text-sm text-amber-200/80">
                이 종목은 판정 대상에 없습니다. 상장 후 253거래일이 지나지 않았거나
                데이터를 받지 못한 종목입니다.
              </div>
            )}

            {row?.x && (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-5">
                <div className="flex items-center gap-2 text-white/70 font-medium">
                  <MinusCircle className="w-4 h-4" /> 스크리닝 대상에서 제외된 종목입니다
                </div>
                <p className="text-sm text-white/50 mt-2">{row.x}</p>
                <p className="text-xs text-white/30 mt-3">
                  모든 패턴 이전에 걸리는 조건이라 패턴별 판정 자체를 하지 않습니다.
                </p>
              </div>
            )}

            {ticker && !shard.isLoading && (
              <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
                <SupplyPanel ticker={ticker} market={market} />
              </div>
            )}

            {row?.p && (
              <div className="space-y-2">
                {ORDER.filter((k) => row.p![k]).map((k) => (
                  <PatternCard
                    key={k}
                    pkey={k}
                    entry={row.p![k]}
                    labels={index.data!.labels[k] ?? []}
                    threshold={index.data!.threshold}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

function PatternCard({
  pkey, entry, labels, threshold,
}: { pkey: PatternKey; entry: SignalEntry; labels: string[]; threshold: number }) {
  const [open, setOpen] = useState(false);
  const { s: state, v: score } = entry;
  const st = STATE[state];
  const conds = entry.c ?? null;
  const hits = entry.h ?? null;
  const e = entry.e;
  const guide = PATTERN_GUIDE[pkey];

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/[0.03]"
      >
        <span className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs shrink-0 ${st.cls}`}>
          <st.Icon className="w-3.5 h-3.5" /> {st.text}
        </span>
        <span className="font-medium">{LABEL[pkey] ?? pkey}</span>
        <span className="ml-auto flex items-center gap-3">
          <span className={`tabular-nums text-sm ${state === "p" ? "text-emerald-400" : "text-white/45"}`}>
            {score}점 <span className="text-white/25">/ {threshold}</span>
          </span>
          <span className="text-white/25 text-xs">{open ? "▾" : "▸"}</span>
        </span>
      </button>

      {/* 접힌 상태에서도 왜 떨어졌는지는 바로 보여야 한다 — 그게 이 화면의 이유다 */}
      {!open && state !== "p" && (
        <p className="px-4 pb-3 -mt-1 text-xs text-white/45">
          {conds
            ? (() => {
                const i = conds.findIndex((c) => !c.o);
                return i < 0 ? "" : `${labels[i] ?? `조건 ${i + 1}`} — ${conds[i].d}`;
              })()
            : hits && hits.length
              ? `구성 패턴 ${hits.length}개 통과 (${hits.map((h) => LABEL[h] ?? h).join(", ")}) — 2개 필요`
              : "구성 패턴 통과 없음 — 2개 필요"}
        </p>
      )}

      {/* 점수는 "패턴 구조가 맞는가", 진입점은 "지금 사는 자리인가" — 다른 질문이다 */}
      {e && (
        <div className="px-4 pb-3 -mt-1">
          <div className="rounded-lg bg-white/[0.03] border border-white/5 px-3 py-2 text-xs">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-white/45">
                원전 진입점 <span className="text-white/70">{e.lb}</span>{" "}
                <b className="font-mono text-white/85">{e.pv.toLocaleString()}</b>
                {e.pd && <span className="text-white/30"> ({e.pd})</span>}
              </span>
              <span className={e.gap > 0.05 ? "text-amber-300" : e.gap < 0 ? "text-white/50" : "text-emerald-400"}>
                현재가 {e.gap >= 0 ? "+" : ""}{(e.gap * 100).toFixed(1)}%
                {e.gap < 0 ? " (돌파 전)" : ""}
              </span>
              {e.st !== undefined && e.sg !== undefined && (
                <span className="text-white/45">
                  원전 손절 <b className="font-mono text-white/70">{e.st.toLocaleString()}</b>
                  <span className={e.sg < -0.08 ? " text-amber-300" : " text-white/50"}>
                    {" "}({(e.sg * 100).toFixed(1)}%)
                  </span>
                </span>
              )}
            </div>
            {ENTRY_STATS[pkey] && (
              <p className="mt-1.5 text-[11px] text-white/35">
                {ENTRY_STATS[pkey]}
              </p>
            )}
          </div>
        </div>
      )}

      {open && (
        <div className="px-4 pb-4 space-y-3 border-t border-white/5 pt-3">
          {conds && (
            <ul className="space-y-1.5">
              {conds.map(({ o: ok, d: val }, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  {ok ? (
                    <CircleCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <CircleX className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                  )}
                  <span className={ok ? "text-white/70" : "text-white/90"}>
                    {labels[i] ?? `조건 ${i + 1}`}
                  </span>
                  <span className="ml-auto tabular-nums text-xs text-white/45">{val}</span>
                </li>
              ))}
            </ul>
          )}
          {hits && (
            <p className="text-sm text-white/60">
              구성: {(guide?.composition) ?? "—"}
              <br />
              통과: {hits.length ? hits.map((h) => LABEL[h] ?? h).join(", ") : "없음"}
            </p>
          )}
          {state === "l" && (
            <p className="text-xs text-amber-300/80">
              필수 조건은 전부 통과했지만 배점 합계가 기준 {threshold}점에 못 미칩니다.
            </p>
          )}
          {guide?.note && (
            <p className="text-xs text-white/35 whitespace-pre-line border-t border-white/5 pt-2">
              {guide.note}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
