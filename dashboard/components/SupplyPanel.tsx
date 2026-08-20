"use client";
import useSWR from "swr";
import { AlertTriangle, ExternalLink } from "lucide-react";
import { fetchFlows, fetchDisclosures } from "@/lib/fetcher";
import type { MarketKey, FlowRow } from "@/lib/types";

/**
 * 종목 하나의 수급·공시 분석. 검색(/lookup)과 패턴 목록 클릭(StockDetailModal) 양쪽에서 쓴다.
 *
 * 수급은 로컬 보강 실행(enrich_local.py)에서만 채워진다 — KRX가 데이터센터 IP를 막아
 * GitHub Actions에서는 받을 수 없다. 공시는 DART라서 자동 실행에서도 들어온다.
 */

const DART_URL = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=";

function pct(v: number | undefined, digits = 2) {
  if (v === undefined || v === null || !Number.isFinite(v)) return null;
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function tone(v: number | undefined) {
  if (v === undefined || !Number.isFinite(v)) return "text-white/30";
  return v > 0 ? "text-rose-400" : v < 0 ? "text-blue-400" : "text-white/50";
}

/**
 * 값이 유니버스에서 어디쯤인지. 경계값은 오름차순이라 넘어선 개수가 곧 백분위다.
 * "외국인 +1.2%"만으로는 큰 값인지 알 수 없다 — 공매도 잔고는 중앙값 0.17%에 최대 10.57%다.
 */
function rankOf(v: number | undefined, breaks?: number[]): number | null {
  if (v === undefined || !Number.isFinite(v) || !breaks || breaks.length < 101) return null;
  let i = 0;
  while (i < 100 && breaks[i + 1] <= v) i += 1;
  return i;
}

function RankTag({ p }: { p: number | null }) {
  if (p === null) return null;
  const top = 100 - p;
  // 양 끝일수록 눈에 띄게 — 가운데는 정보가 거의 없다
  const strong = top <= 10 || top >= 90;
  return (
    <span className={`text-[10px] ${strong ? "text-amber-300" : "text-white/30"}`}>
      {top <= 50 ? `상위 ${Math.max(top, 1)}%` : `하위 ${101 - top}%`}
    </span>
  );
}

/** 순매수는 시총 대비 비율이라 종목 크기와 무관하게 비교된다 */
function FlowCell({ label, v, rank }: { label: string; v?: number; rank: number | null }) {
  const text = pct(v);
  return (
    <div>
      <div className="text-[11px] text-white/40">{label}</div>
      <div className={`text-sm font-mono tabular-nums ${tone(v)}`}>{text ?? "—"}</div>
      <RankTag p={rank} />
    </div>
  );
}

export function SupplyPanel({ ticker, market = "kr" }: { ticker: string; market?: MarketKey }) {
  const flows = useSWR(["flows", market], () => fetchFlows(market));
  const disc = useSWR(["disc", market], () => fetchDisclosures(market));

  const row: FlowRow | undefined = flows.data?.tickers?.[ticker];
  const dist = flows.data?.dist;
  const r = (k: keyof FlowRow) => rankOf(row?.[k], dist?.[k as string]);
  const d = disc.data?.tickers?.[ticker];
  const critical = d?.items.filter((i) => i.lv === "c") ?? [];

  return (
    <div className="space-y-4">
      {/* 자본 조정은 과거 가격과 오늘 가격의 비교 자체를 무너뜨린다 — 제일 먼저 보여야 한다 */}
      {critical.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3">
          <div className="flex items-center gap-2 text-amber-300 text-sm font-medium">
            <AlertTriangle className="w-4 h-4" /> 자본 조정 공시 — 과거 가격과 직접 비교 불가
          </div>
          <ul className="mt-2 space-y-1">
            {critical.map((i) => (
              <li key={i.no} className="text-xs text-amber-100/80 flex gap-2">
                <span className="tabular-nums text-amber-200/60">{i.d}</span>
                <a
                  href={`${DART_URL}${i.no}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline inline-flex items-center gap-1"
                >
                  {i.nm}
                  <ExternalLink className="w-3 h-3 opacity-50" />
                </a>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] text-amber-200/50">
            무상증자·액면분할이 있으면 주가가 기계적으로 바뀝니다. 그 이전에 산 가격을
            지금 가격과 그대로 비교하면 손실이 부풀려 보입니다.
          </p>
        </div>
      )}

      <section>
        <h4 className="text-xs font-semibold text-white/50 mb-2">외국인 · 기관 순매수 (시총 대비)</h4>
        {flows.isLoading ? (
          <div className="h-12 rounded bg-white/5 animate-pulse" />
        ) : !flows.data ? (
          <p className="text-xs text-white/35">
            수급 데이터가 아직 없습니다 — KRX가 클라우드 IP를 막아 로컬에서
            <code className="mx-1 text-white/50">enrich_local.py</code>를 실행해야 채워집니다.
          </p>
        ) : !row ? (
          <p className="text-xs text-white/35">이 종목은 수급 수집 대상에 없습니다.</p>
        ) : (
          <>
            <div className="grid grid-cols-4 gap-3">
              <FlowCell label="외국인 20일" v={row.f20} rank={r("f20")} />
              <FlowCell label="기관 20일" v={row.i20} rank={r("i20")} />
              <FlowCell label="외국인 60일" v={row.f60} rank={r("f60")} />
              <FlowCell label="기관 60일" v={row.i60} rank={r("i60")} />
            </div>
            <div className="grid grid-cols-4 gap-3 mt-3 pt-3 border-t border-white/5">
              <div>
                <div className="text-[11px] text-white/40">공매도 잔고</div>
                <div className="text-sm font-mono tabular-nums text-white/80">
                  {row.sb !== undefined ? `${row.sb.toFixed(2)}%` : "—"}
                </div>
                <RankTag p={r("sb")} />
              </div>
              <div>
                <div className="text-[11px] text-white/40">공매도 거래</div>
                <div className="text-sm font-mono tabular-nums text-white/80">
                  {row.sv !== undefined ? `${row.sv.toFixed(2)}%` : "—"}
                </div>
                <RankTag p={r("sv")} />
              </div>
              <div>
                <div className="text-[11px] text-white/40">PER / PBR</div>
                <div className="text-sm font-mono tabular-nums text-white/80">
                  {row.per ?? "—"} / {row.pbr ?? "—"}
                </div>
              </div>
              <div>
                <div className="text-[11px] text-white/40">배당수익률</div>
                <div className="text-sm font-mono tabular-nums text-white/80">
                  {row.div !== undefined ? `${row.div.toFixed(2)}%` : "—"}
                </div>
              </div>
            </div>
            <p className="mt-2 text-[11px] text-white/30">
              기준 {flows.data.bar_date} · 순매수는 기간 누적을 시가총액으로 나눈 값입니다.
              원화 절대액은 대형주가 항상 커서 종목 간 비교가 안 됩니다.
              백분위는 이 시장 전 종목 중 위치입니다 — 사실 진술이며 예측이 아닙니다.
              <b className="text-white/45"> 점수에는 반영되지 않습니다</b> — 선정력이 아직 실측되지 않았습니다.
            </p>
          </>
        )}
      </section>

      <section>
        <h4 className="text-xs font-semibold text-white/50 mb-2">주요 공시</h4>
        {disc.isLoading ? (
          <div className="h-12 rounded bg-white/5 animate-pulse" />
        ) : !d ? (
          <p className="text-xs text-white/35">
            공시는 패턴 목록에 오른 종목만 수집합니다.
          </p>
        ) : d.items.length === 0 ? (
          <p className="text-xs text-white/35">{d.from} 이후 주요 공시가 없습니다.</p>
        ) : (
          <>
            <ul className="space-y-1 max-h-52 overflow-y-auto pr-1">
              {d.items.map((i) => (
                <li key={i.no} className="flex gap-2 text-xs">
                  <span className="tabular-nums text-white/35 shrink-0">{i.d}</span>
                  <a
                    href={`${DART_URL}${i.no}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={`hover:underline ${i.lv === "c" ? "text-amber-300" : "text-white/70"}`}
                  >
                    {i.nm}
                  </a>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11px] text-white/30">
              {d.from} 이후 · 임원 소유상황 등 {d.dropped.toLocaleString()}건은 생략했습니다.
              제목을 누르면 DART 원문이 열립니다.
            </p>
          </>
        )}
      </section>
    </div>
  );
}
