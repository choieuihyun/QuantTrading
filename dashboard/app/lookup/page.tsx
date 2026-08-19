"use client";
import useSWR from "swr";
import { useMemo, useState } from "react";
import { Search, CircleCheck, CircleX, MinusCircle, AlertCircle } from "lucide-react";
import { Header } from "@/components/Header";
import { DataError } from "@/components/DataError";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchPrices, fetchSignalIndex, fetchSignalShard, shardOf } from "@/lib/fetcher";
import { PATTERN_GUIDE } from "@/lib/patternGuide";
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
