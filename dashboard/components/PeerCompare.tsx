"use client";
import type { Stock } from "@/lib/types";

interface Props {
  stock: Stock;
  universe: Stock[];
}

// KSIC 대분류(앞 2자리) — 비교 그룹 이름 표시용. 없는 코드는 코드 자체를 보여준다.
const KSIC2: Record<string, string> = {
  "10": "식료품", "13": "섬유", "17": "펄프·종이", "18": "인쇄", "19": "석유정제",
  "20": "화학", "21": "의약품", "22": "고무·플라스틱", "23": "비금속광물", "24": "1차금속",
  "25": "금속가공", "26": "전자·반도체", "27": "의료·정밀기기", "28": "전기장비",
  "29": "기계·장비", "30": "자동차", "31": "운송장비", "32": "가구", "33": "기타제조",
  "35": "전기·가스", "41": "건설", "42": "토목", "45": "자동차판매", "46": "도매",
  "47": "소매", "49": "육상운송", "50": "수상운송", "51": "항공", "52": "물류",
  "58": "출판", "59": "영상·음악", "61": "통신", "62": "소프트웨어", "63": "정보서비스",
  "64": "금융", "65": "보험", "66": "금융지원", "68": "부동산", "70": "연구개발",
  "71": "전문서비스", "72": "건축기술", "73": "기타과학기술", "86": "보건", "91": "스포츠·오락",
};

function fmtMult(v?: number) {
  return v == null ? "-" : v.toFixed(1);
}
function fmtPct(v?: number) {
  return v == null ? "-" : `${(v * 100).toFixed(1)}%`;
}

export function PeerCompare({ stock, universe }: Props) {
  const code = stock.induty;
  if (!code) return null;

  // 세부업종(3자리)으로 먼저 묶고, 비교 대상이 부족하면 대분류(2자리)로 넓힌다.
  const byPrefix = (n: number) =>
    universe.filter((s) => s.induty && s.induty.slice(0, n) === code.slice(0, n));

  let peers = byPrefix(3);
  let level = 3;
  if (peers.length < 2) {
    peers = byPrefix(2);
    level = 2;
  }
  if (peers.length < 2) return null;

  // 종목 중복 제거(여러 패턴에 동시 등장) 후 시총 순
  const seen = new Set<string>();
  const rows = peers
    .filter((s) => (seen.has(s.ticker) ? false : (seen.add(s.ticker), true)))
    .sort((a, b) => (b.marcap ?? 0) - (a.marcap ?? 0))
    .slice(0, 8);

  const groupName = KSIC2[code.slice(0, 2)] ?? `업종 ${code.slice(0, 2)}`;

  return (
    <div>
      <p className="text-xs text-white/40 mb-1.5">
        동종업계 비교 · {groupName}
        <span className="text-white/25">
          {level === 3 ? " (세부업종)" : " (대분류)"} · 스크리닝 통과 종목 중
        </span>
      </p>
      <div className="rounded-lg border border-white/10 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="bg-white/5 text-white/40">
              <th className="px-2.5 py-1.5 text-left font-medium">종목</th>
              <th className="px-2.5 py-1.5 text-right font-medium">PER</th>
              <th className="px-2.5 py-1.5 text-right font-medium">PBR</th>
              <th className="px-2.5 py-1.5 text-right font-medium">ROE</th>
              <th className="px-2.5 py-1.5 text-right font-medium">영업이익률</th>
              <th className="px-2.5 py-1.5 text-right font-medium">재고YoY</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const self = s.ticker === stock.ticker;
              return (
                <tr
                  key={s.ticker}
                  className={`border-t border-white/5 ${self ? "bg-indigo-500/10" : ""}`}
                >
                  <td className={`px-2.5 py-1.5 ${self ? "text-indigo-300 font-semibold" : "text-white/80"}`}>
                    {s.name}
                  </td>
                  <td className="px-2.5 py-1.5 text-right font-mono text-white/70">{fmtMult(s.per)}</td>
                  <td className="px-2.5 py-1.5 text-right font-mono text-white/70">{fmtMult(s.pbr)}</td>
                  <td className="px-2.5 py-1.5 text-right font-mono text-white/70">{fmtPct(s.roe)}</td>
                  <td className="px-2.5 py-1.5 text-right font-mono text-white/70">{fmtPct(s.op_margin)}</td>
                  <td
                    className={`px-2.5 py-1.5 text-right font-mono ${
                      s.inventory_yoy != null && s.inventory_yoy < 0 ? "text-emerald-400" : "text-white/70"
                    }`}
                  >
                    {fmtPct(s.inventory_yoy)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
