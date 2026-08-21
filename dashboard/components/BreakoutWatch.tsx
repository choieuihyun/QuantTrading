"use client";
import useSWR from "swr";
import { useState } from "react";
import { Bell, ChevronDown } from "lucide-react";
import { fetchWatchlist } from "@/lib/fetcher";
import type { MarketKey, WatchRow } from "@/lib/types";

/**
 * 돌파 대기 — 아직 발동하지 않은 패턴의 발동가.
 *
 * 스크리너는 하루 3번만 돈다. 돌파는 장중에 일어나므로 패턴 목록에 뜰 때는 이미 며칠 지난 뒤다.
 * 발동가를 미리 알면 증권사 앱에 알림을 걸어둘 수 있다 — 이 화면의 용도는 그것뿐이다.
 *
 * 매수 신호가 아니다. 돌파 지점에서 사는 것이 이득이라는 실측 근거는 없다.
 */

const LABEL: Record<string, { name: string; cls: string }> = {
  vcp:    { name: "VCP",     cls: "text-violet-300 border-violet-400/30 bg-violet-500/10" },
  darvas: { name: "Darvas",  cls: "text-sky-300 border-sky-400/30 bg-sky-500/10" },
  stage2: { name: "Stage 2", cls: "text-emerald-300 border-emerald-400/30 bg-emerald-500/10" },
};

const won = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 });

function Row({ r }: { r: WatchRow }) {
  const tag = LABEL[r.k] ?? { name: r.k, cls: "text-white/50 border-white/15 bg-white/5" };
  // 가까울수록 눈에 띄게 — 3% 이내면 며칠 안에 닿을 수 있는 거리다
  const hot = r.g <= 0.03;
  return (
    <tr className="border-t border-white/5 hover:bg-white/[0.03]">
      <td className="px-3 py-2">
        <a
          href={`https://finance.naver.com/item/main.naver?code=${r.t}`}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:underline"
        >
          {r.n}
        </a>
        <span className="ml-1.5 text-[11px] text-white/30 font-mono">{r.t}</span>
      </td>
      <td className="px-3 py-2">
        <span className={`text-[11px] px-1.5 py-0.5 rounded border ${tag.cls}`}>{tag.name}</span>
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-white/60">{won(r.pr)}</td>
      <td className="px-3 py-2 text-right tabular-nums font-medium">{won(r.tg)}</td>
      <td className={`px-3 py-2 text-right tabular-nums ${hot ? "text-amber-300" : "text-white/55"}`}>
        +{(r.g * 100).toFixed(1)}%
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-white/45">
        {r.st ? won(r.st) : "—"}
      </td>
      <td className={`px-3 py-2 text-right tabular-nums ${
        r.sl != null && r.sl < -0.15 ? "text-amber-300/80" : "text-white/45"}`}>
        {r.sl != null ? `${(r.sl * 100).toFixed(0)}%` : "—"}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-white/40">{r.rs ?? "—"}</td>
    </tr>
  );
}

export function BreakoutWatch({ market = "kr" }: { market?: MarketKey }) {
  const { data, isLoading } = useSWR(["watch", market], () => fetchWatchlist(market));
  const [open, setOpen] = useState(false);

  const rows = data?.rows ?? [];
  const shown = open ? rows : rows.slice(0, 10);
  const near = rows.filter((r) => r.g <= 0.03).length;

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.02] overflow-hidden">
      <div className="px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2 flex-wrap">
          <Bell className="w-4 h-4 text-amber-300/80" />
          <h2 className="font-semibold">돌파 대기</h2>
          {rows.length > 0 && (
            <span className="text-xs text-white/40">
              {rows.length}종목 · 3% 이내 <b className="text-amber-300/90">{near}</b>
            </span>
          )}
          {data?.bar_date && (
            <span className="ml-auto text-[11px] text-white/30">기준 {data.bar_date}</span>
          )}
        </div>
        <p className="mt-1.5 text-[11px] text-white/40 leading-relaxed">
          발동가를 넘으면 그 패턴의 조건이 충족됩니다. 스크리너는 하루 3번만 돌아서 돌파 순간을
          놓치므로, <b className="text-white/55">증권사 앱에 발동가로 알림을 걸어두는 용도</b>입니다.
          <b className="text-amber-300/70"> 매수 신호가 아닙니다</b> — 돌파 지점 매수가 유리하다는
          실측 근거는 없습니다.
        </p>
      </div>

      {isLoading ? (
        <div className="h-32 animate-pulse bg-white/[0.02]" />
      ) : rows.length === 0 ? (
        <p className="px-4 py-6 text-sm text-white/35">
          발동가 15% 이내에 온 종목이 없습니다. 목록이 비는 것도 정보입니다 —
          지금은 돌파를 기다릴 자리가 없다는 뜻입니다.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-[11px] text-white/35">
                <tr>
                  <th className="text-left px-3 py-2 font-medium">종목</th>
                  <th className="text-left px-3 py-2 font-medium">대기 중인 패턴</th>
                  <th className="text-right px-3 py-2 font-medium">현재가</th>
                  <th className="text-right px-3 py-2 font-medium">발동가</th>
                  <th className="text-right px-3 py-2 font-medium">거리</th>
                  <th className="text-right px-3 py-2 font-medium">원전 손절</th>
                  <th className="text-right px-3 py-2 font-medium">손실폭</th>
                  <th className="text-right px-3 py-2 font-medium">RS</th>
                </tr>
              </thead>
              <tbody>{shown.map((r) => <Row key={`${r.t}-${r.k}`} r={r} />)}</tbody>
            </table>
          </div>
          {rows.length > 10 && (
            <button
              onClick={() => setOpen((v) => !v)}
              className="w-full py-2 text-xs text-white/45 hover:text-white/70 hover:bg-white/[0.03] border-t border-white/5 inline-flex items-center justify-center gap-1"
            >
              {open ? "접기" : `${rows.length - 10}종목 더 보기`}
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>
          )}
          <p className="px-4 py-2.5 text-[11px] text-white/30 border-t border-white/5 leading-relaxed">
            <b className="text-white/45">손실폭</b>은 발동가에 사서 원전 손절을 지켰을 때 감수하는 폭입니다.
            패턴마다 크게 다릅니다 — Darvas는 박스 바닥(−10~18%), Stage 2는 거래범위 하단(−20% 이상)이라
            Minervini의 −8% 기준과는 다른 규칙입니다.
            <b className="text-white/45"> VCP</b>는 게이트가 이미 통과된 상태에서 피벗이 진입가이고,
            나머지 둘은 발동가를 넘어야 패턴이 뜹니다.
          </p>
        </>
      )}
    </section>
  );
}
