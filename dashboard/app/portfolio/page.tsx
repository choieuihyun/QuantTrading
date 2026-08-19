"use client";
import useSWR from "swr";
import { useEffect, useMemo, useState } from "react";
import {
  Briefcase, Plus, Search, Trash2, LogOut, RotateCcw,
  Download, Upload, AlertTriangle, TrendingUp, TrendingDown,
} from "lucide-react";
import { Header } from "@/components/Header";
import { DataError } from "@/components/DataError";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchPrices } from "@/lib/fetcher";
import * as pf from "@/lib/portfolio";
import type { MarketKey, PatternKey, Position } from "@/lib/types";

const MARKETS: { key: MarketKey; label: string; flag: string; unit: string }[] = [
  { key: "kr",     label: "한국",  flag: "🇰🇷", unit: "원" },
  { key: "us",     label: "미국",  flag: "🇺🇸", unit: "$"  },
  { key: "crypto", label: "코인",  flag: "₿",  unit: "원" },
];

const PATTERNS: PatternKey[] = [
  "common_trend", "common_accum", "common_all",
  "canslim", "vcp", "stage2", "wyckoff", "darvas", "p1", "p2", "p3",
];

const PATTERN_LABEL: Record<string, string> = {
  common_trend: "돌파 공통", common_accum: "매집 공통", common_all: "내 패턴 공통",
  canslim: "CAN SLIM", vcp: "VCP", stage2: "Stage 2", wyckoff: "Wyckoff",
  darvas: "Darvas", p1: "정배열매집", p2: "5일선추세", p3: "눌림목",
};

function pct(v: number | null, digits = 2) {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(digits)}%`;
}

function money(v: number | null, unit: string) {
  if (v === null || !Number.isFinite(v)) return "—";
  const s = Math.abs(v) >= 1000 ? Math.round(v).toLocaleString() : v.toFixed(2);
  return unit === "$" ? `$${s}` : `${s}원`;
}

function tone(v: number | null) {
  if (v === null) return "text-white/40";
  return v > 0 ? "text-rose-400" : v < 0 ? "text-blue-400" : "text-white/60";
}

/** toISOString은 UTC라 KST 오전 0~9시에 하루 밀린다. 진입일이 밀리면 기록 자체가 틀어진다. */
function today() {
  return new Date().toLocaleDateString("sv-SE");
}

export default function PortfolioPage() {
  const [market, setMarket] = useState<MarketKey>("kr");
  const [positions, setPositions] = useState<Position[]>([]);
  const [ready, setReady] = useState(false);
  const [showClosed, setShowClosed] = useState(false);

  // localStorage는 서버 렌더 시점에 없다 — 마운트 후에 읽는다
  useEffect(() => {
    setPositions(pf.load());
    setReady(true);
  }, []);

  function commit(next: Position[]) {
    setPositions(next);
    pf.save(next);
  }

  const { data, error, isLoading } = useSWR(["prices", market], () => fetchPrices(market));

  const prices = data?.prices ?? {};
  const names = data?.names ?? {};

  const rows = useMemo(
    () => positions.filter((p) => p.market === market).map((p) => pf.valuePosition(p, prices)),
    [positions, market, prices]
  );
  const open = rows.filter((r) => !r.closed);
  const closed = rows.filter((r) => r.closed);
  const openTotals = pf.totals(open);
  const closedTotals = pf.totals(closed);
  const unit = MARKETS.find((m) => m.key === market)!.unit;

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white">
      <Header />
      <main className="mx-auto max-w-6xl px-4 py-6 space-y-6">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Briefcase className="w-6 h-6 text-emerald-400" /> 가상 매매
            </h1>
            <p className="text-sm text-white/50 mt-1">
              실제 주문이 아닙니다. 패턴 목록에서 고른 종목을 담아두고 경과만 추적합니다.
            </p>
          </div>
          <div className="flex gap-1">
            {MARKETS.map((m) => (
              <button
                key={m.key}
                onClick={() => setMarket(m.key)}
                className={`px-3 py-1.5 rounded-lg text-sm transition ${
                  market === m.key ? "bg-white/15 text-white" : "text-white/50 hover:bg-white/5"
                }`}
              >
                {m.flag} {m.label}
              </button>
            ))}
          </div>
        </div>

        <StorageNotice />

        {error ? (
          <DataError err={error} collection="prices" />
        ) : isLoading || !ready ? (
          <Skeleton className="h-64 w-full" />
        ) : !data ? (
          <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/45">
            이 시장의 시세가 아직 없습니다. 스크리너를 <b className="text-white/70">{market}</b> 시장으로
            한 번 돌리면 채워집니다 (읽기 권한 문제가 아니라 데이터가 없는 상태입니다).
          </div>
        ) : (
          <>
            <PriceStamp date={data.market_date} count={data.count} market={market} />

            <AddForm
              market={market}
              prices={prices}
              names={names}
              unit={unit}
              onAdd={(input) => commit(pf.add(positions, input))}
            />

            <Summary
              label="보유 중"
              t={openTotals}
              unit={unit}
              count={open.length}
            />

            <PositionTable
              rows={open}
              unit={unit}
              emptyText="아직 담은 종목이 없습니다. 위에서 검색해 추가하세요."
              onClose={(id, price) => commit(pf.close(positions, id, today(), price))}
              onRemove={(id) => commit(pf.remove(positions, id))}
            />

            {closed.length > 0 && (
              <div className="space-y-3">
                <button
                  onClick={() => setShowClosed((v) => !v)}
                  className="text-sm text-white/60 hover:text-white/90"
                >
                  {showClosed ? "▾" : "▸"} 청산 기록 {closed.length}건
                  <span className={`ml-2 ${tone(closedTotals.pnlPct)}`}>
                    {pct(closedTotals.pnlPct)}
                  </span>
                </button>
                {showClosed && (
                  <>
                    <Summary label="청산 완료" t={closedTotals} unit={unit} count={closed.length} />
                    <PositionTable
                      rows={closed}
                      unit={unit}
                      emptyText=""
                      onReopen={(id) => commit(pf.reopen(positions, id))}
                      onRemove={(id) => commit(pf.remove(positions, id))}
                    />
                  </>
                )}
              </div>
            )}

            <PatternRollup rows={rows} unit={unit} />

            <Backup positions={positions} onReplace={commit} />
          </>
        )}
      </main>
    </div>
  );
}

function StorageNotice() {
  return (
    <div className="flex gap-2 rounded-lg border border-amber-500/25 bg-amber-500/5 px-3 py-2 text-xs text-amber-200/80">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <p>
        기록은 <b>이 브라우저에만</b> 저장됩니다. 로그인이 없는 프로젝트라 서버에 두면
        누구나 열람·수정할 수 있어서입니다. 기기를 옮기려면 맨 아래 내보내기를 쓰세요.
      </p>
    </div>
  );
}

function PriceStamp({ date, count, market }: { date: string; count: number; market: MarketKey }) {
  // 주말·공휴일에도 경고가 뜨면 경고를 무시하게 된다 — 거래일 기준 3일 넘게 묵었을 때만 띄운다
  const ageDays = Math.floor(
    (new Date(today()).getTime() - new Date(date).getTime()) / 86_400_000
  );
  const stale = ageDays > 4;
  return (
    <p className="text-xs text-white/40">
      평가 기준 <b className={stale ? "text-amber-300" : "text-white/70"}>{date}</b> 종가
      · {count.toLocaleString()}종목 · 실시간 아님 · 수익률은 왕복 거래비용{" "}
      {(pf.roundTripCost(market) * 100).toFixed(2)}% 반영(성적표·통계와 같은 기준)
      {stale && ` — ${ageDays}일 묵었습니다. 스크리너가 돌지 않고 있습니다.`}
    </p>
  );
}

function Summary({
  label, t, unit, count,
}: { label: string; t: pf.Totals; unit: string; count: number }) {
  const cells = [
    { k: "종목", v: `${count}개` },
    { k: "투입금", v: money(t.cost, unit) },
    { k: "평가금", v: money(t.value, unit) },
    { k: "손익", v: money(t.pnlAmount, unit), tone: tone(t.pnlPct) },
    { k: "수익률", v: pct(t.pnlPct), tone: tone(t.pnlPct) },
    { k: "승/패", v: `${t.wins} / ${t.losses}` },
  ];
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-medium text-white/70">{label}</span>
        {t.unpriced > 0 && (
          <span className="text-xs text-amber-300">
            시세 없음 {t.unpriced}건은 합계에서 빠짐
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {cells.map((c) => (
          <div key={c.k}>
            <div className="text-[11px] text-white/40">{c.k}</div>
            <div className={`text-lg font-semibold tabular-nums ${c.tone ?? "text-white"}`}>
              {c.v}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function AddForm({
  market, prices, names, unit, onAdd,
}: {
  market: MarketKey;
  prices: Record<string, number>;
  names: Record<string, string>;
  unit: string;
  onAdd: (i: {
    market: MarketKey; ticker: string; name: string; entryDate: string;
    entryPrice: number; shares: number; pattern?: PatternKey | null; note?: string;
  }) => void;
}) {
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState<{ ticker: string; name: string } | null>(null);
  const [entryDate, setEntryDate] = useState(today());
  const [entryPrice, setEntryPrice] = useState("");
  const [shares, setShares] = useState("");
  const [pattern, setPattern] = useState<PatternKey | "">("");

  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    const out: { ticker: string; name: string }[] = [];
    for (const [t, n] of Object.entries(names)) {
      if (t.toLowerCase().includes(s) || n.toLowerCase().includes(s)) {
        out.push({ ticker: t, name: n });
        if (out.length >= 8) break;
      }
    }
    return out;
  }, [q, names]);

  function pick(m: { ticker: string; name: string }) {
    setPicked(m);
    setQ(`${m.name} (${m.ticker})`);
    // 진입가를 비워두면 오늘 종가를 기본값으로 — 오늘 담는 경우가 대부분이다
    if (!entryPrice && prices[m.ticker]) setEntryPrice(String(prices[m.ticker]));
  }

  const price = Number(entryPrice);
  const qty = Number(shares);
  const valid =
    picked !== null && Number.isFinite(price) && price > 0 &&
    Number.isFinite(qty) && qty > 0 && Boolean(entryDate);

  function submit() {
    if (!valid || !picked) return;
    onAdd({
      market, ticker: picked.ticker, name: picked.name,
      entryDate, entryPrice: price, shares: qty,
      pattern: pattern || null,
    });
    setQ(""); setPicked(null); setEntryPrice(""); setShares(""); setPattern("");
  }

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="text-sm font-medium text-white/70 flex items-center gap-2">
        <Plus className="w-4 h-4" /> 종목 담기
      </div>

      <div className="grid gap-3 md:grid-cols-[2fr_1fr_1fr_1fr_1.2fr_auto]">
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
          <input
            value={q}
            onChange={(e) => { setQ(e.target.value); setPicked(null); }}
            placeholder="종목명 또는 코드"
            className="w-full rounded-lg bg-white/5 border border-white/10 pl-9 pr-3 py-2 text-sm
                       outline-none focus:border-emerald-400/50"
          />
          {!picked && matches.length > 0 && (
            <ul className="absolute z-20 mt-1 w-full rounded-lg border border-white/10
                           bg-[#12121a] shadow-xl overflow-hidden">
              {matches.map((m) => (
                <li key={m.ticker}>
                  <button
                    onClick={() => pick(m)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-white/10 flex justify-between"
                  >
                    <span>{m.name}</span>
                    <span className="text-white/40 tabular-nums">
                      {m.ticker} · {money(prices[m.ticker] ?? null, unit)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <input
          type="date" value={entryDate} onChange={(e) => setEntryDate(e.target.value)}
          max={today()}
          className="rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm
                     outline-none focus:border-emerald-400/50"
        />
        <input
          value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)}
          inputMode="decimal" placeholder="매수가"
          className="rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm tabular-nums
                     outline-none focus:border-emerald-400/50"
        />
        <input
          value={shares} onChange={(e) => setShares(e.target.value)}
          inputMode="decimal" placeholder="수량"
          className="rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm tabular-nums
                     outline-none focus:border-emerald-400/50"
        />
        <select
          value={pattern} onChange={(e) => setPattern(e.target.value as PatternKey | "")}
          className="rounded-lg bg-white/5 border border-white/10 px-3 py-2 text-sm
                     outline-none focus:border-emerald-400/50"
        >
          <option value="">패턴 선택 안 함</option>
          {PATTERNS.map((p) => (
            <option key={p} value={p}>{PATTERN_LABEL[p]}</option>
          ))}
        </select>
        <button
          onClick={submit} disabled={!valid}
          className="rounded-lg px-4 py-2 text-sm font-medium bg-emerald-500/20 text-emerald-300
                     border border-emerald-400/30 hover:bg-emerald-500/30
                     disabled:opacity-30 disabled:cursor-not-allowed"
        >
          담기
        </button>
      </div>

      <p className="text-xs text-white/35">
        과거 날짜로 담을 때 매수가는 직접 입력해야 합니다 — 저장된 시세가 최신 하루치뿐이라
        그날 종가를 자동으로 채울 수 없습니다.
      </p>
    </div>
  );
}

function PositionTable({
  rows, unit, emptyText, onClose, onReopen, onRemove,
}: {
  rows: pf.Valued[];
  unit: string;
  emptyText: string;
  onClose?: (id: string, price: number) => void;
  onReopen?: (id: string) => void;
  onRemove: (id: string) => void;
}) {
  if (rows.length === 0) {
    return emptyText ? (
      <div className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-white/40">
        {emptyText}
      </div>
    ) : null;
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-white/10">
      <table className="w-full text-sm min-w-[720px]">
        <thead className="bg-white/[0.03] text-white/50 text-xs">
          <tr>
            {["종목", "패턴", "진입일", "보유", "매수가", "현재가", "수량", "손익", "수익률(비용반영)", ""]
              .map((h) => (
                <th key={h} className="px-3 py-2 text-left font-medium whitespace-nowrap">{h}</th>
              ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-white/5 hover:bg-white/[0.02]">
              <td className="px-3 py-2">
                <div className="font-medium">{r.name}</div>
                <div className="text-xs text-white/35 tabular-nums">{r.ticker}</div>
              </td>
              <td className="px-3 py-2 text-xs text-white/50">
                {r.pattern ? PATTERN_LABEL[r.pattern] ?? r.pattern : "—"}
              </td>
              <td className="px-3 py-2 tabular-nums text-white/60">{r.entryDate}</td>
              <td className="px-3 py-2 tabular-nums text-white/60">{r.heldDays}일</td>
              <td className="px-3 py-2 tabular-nums">
                {money(r.entryPrice, unit)}
                {r.splitFactor && (
                  <span
                    title={`현재가의 약 ${r.splitFactor}배입니다. 액면분할·무상증자가 있었다면 매수가를 ${money(r.entryPrice / r.splitFactor, unit)}로 고쳐야 수익률이 맞습니다.`}
                    className="ml-1 text-[10px] text-amber-300 align-super"
                  >분할?</span>
                )}
              </td>
              <td className="px-3 py-2 tabular-nums">
                {r.nowPrice === null
                  ? <span className="text-amber-300 text-xs">시세 없음</span>
                  : money(r.nowPrice, unit)}
                {r.closed && <span className="ml-1 text-[10px] text-white/35">청산</span>}
              </td>
              <td className="px-3 py-2 tabular-nums text-white/60">{r.shares}</td>
              <td className={`px-3 py-2 tabular-nums ${tone(r.pnlPct)}`}>
                {money(r.pnlAmount, unit)}
              </td>
              <td className={`px-3 py-2 tabular-nums font-semibold ${tone(r.pnlPct)}`}>
                <span className="inline-flex items-center gap-1">
                  {r.pnlPct !== null && r.pnlPct > 0 && <TrendingUp className="w-3.5 h-3.5" />}
                  {r.pnlPct !== null && r.pnlPct < 0 && <TrendingDown className="w-3.5 h-3.5" />}
                  {pct(r.pnlPct)}
                </span>
              </td>
              <td className="px-3 py-2">
                <div className="flex gap-1 justify-end">
                  {onClose && r.nowPrice !== null && (
                    <button
                      onClick={() => onClose(r.id, r.nowPrice!)}
                      title="현재가로 청산"
                      className="p-1.5 rounded hover:bg-white/10 text-white/40 hover:text-white/80"
                    >
                      <LogOut className="w-4 h-4" />
                    </button>
                  )}
                  {onReopen && (
                    <button
                      onClick={() => onReopen(r.id)}
                      title="청산 취소"
                      className="p-1.5 rounded hover:bg-white/10 text-white/40 hover:text-white/80"
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={() => onRemove(r.id)}
                    title="기록 삭제"
                    className="p-1.5 rounded hover:bg-rose-500/15 text-white/40 hover:text-rose-300"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 어느 패턴에서 담은 게 나았는지 — 성적표가 '화면에 떴던 종목 전체'를 재는 것과 달리
 *  여기는 '내가 실제로 고른 것'만 잰다. 표본이 얇으니 판단 근거로 쓰기 전에 건수를 봐야 한다. */
function PatternRollup({ rows, unit }: { rows: pf.Valued[]; unit: string }) {
  const roll = pf.byPattern(rows);
  if (roll.length === 0) return null;
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4">
      <div className="text-sm font-medium text-white/70 mb-1">패턴별 내 성적</div>
      <p className="text-xs text-white/35 mb-3">
        내가 담은 종목만 집계합니다. 건수가 적으면 우연입니다 — 이번 실측에서 63스캔·수천 건으로도
        패턴 간 차이가 노이즈와 구별되지 않았습니다.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[420px]">
          <thead className="text-white/45 text-xs">
            <tr>
              {["패턴", "건수", "승", "평균 수익률", "누적 손익"].map((h) => (
                <th key={h} className="px-2 py-1.5 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {roll.map((r) => (
              <tr key={r.pattern} className="border-t border-white/5">
                <td className="px-2 py-1.5">{PATTERN_LABEL[r.pattern] ?? r.pattern}</td>
                <td className="px-2 py-1.5 tabular-nums text-white/60">{r.n}</td>
                <td className="px-2 py-1.5 tabular-nums text-white/60">{r.wins}</td>
                <td className={`px-2 py-1.5 tabular-nums font-medium ${tone(r.avgPct)}`}>
                  {pct(r.avgPct)}
                </td>
                <td className={`px-2 py-1.5 tabular-nums ${tone(r.totalPnl)}`}>
                  {money(r.totalPnl, unit)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Backup({
  positions, onReplace,
}: { positions: Position[]; onReplace: (p: Position[]) => void }) {
  const [msg, setMsg] = useState("");

  function download() {
    const blob = new Blob([pf.toJSON(positions)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `portfolio-${today()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then((text) => {
      const rows = pf.fromJSON(text);
      if (!rows) { setMsg("읽을 수 없는 파일입니다."); return; }
      onReplace(rows);
      setMsg(`${rows.length}건을 불러왔습니다 — 기존 기록은 대체되었습니다.`);
    });
    e.target.value = "";
  }

  return (
    <div className="flex items-center gap-3 flex-wrap pt-2 text-sm">
      <button
        onClick={download} disabled={positions.length === 0}
        className="inline-flex items-center gap-1.5 rounded-lg border border-white/10
                   px-3 py-1.5 text-white/60 hover:bg-white/5 disabled:opacity-30"
      >
        <Download className="w-4 h-4" /> 내보내기
      </button>
      <label className="inline-flex items-center gap-1.5 rounded-lg border border-white/10
                        px-3 py-1.5 text-white/60 hover:bg-white/5 cursor-pointer">
        <Upload className="w-4 h-4" /> 가져오기
        <input type="file" accept="application/json" onChange={upload} className="hidden" />
      </label>
      {msg && <span className="text-xs text-white/50">{msg}</span>}
    </div>
  );
}
