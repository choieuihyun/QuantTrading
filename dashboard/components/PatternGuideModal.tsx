"use client";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import type { PatternKey } from "@/lib/types";
import { PATTERN_GUIDE } from "@/lib/patternGuide";

interface Props {
  pattern: PatternKey | null;
  onClose: () => void;
}

export function PatternGuideModal({ pattern, onClose }: Props) {
  if (!pattern) return null;
  const g = PATTERN_GUIDE[pattern];

  return (
    <Dialog open={!!pattern} onOpenChange={onClose}>
      <DialogContent className="bg-[#0f1117] border-white/10 text-white max-w-lg max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold">{g.title}</DialogTitle>
        </DialogHeader>

        {g.author && <p className="text-xs text-white/40 -mt-1">{g.author}</p>}

        <p className="text-sm text-indigo-300 leading-relaxed">{g.tagline}</p>

        {g.composition && (
          <div className="rounded-lg bg-white/5 border border-white/10 px-3 py-2">
            <span className="text-xs text-white/40">구성</span>
            <p className="text-sm text-white/80 mt-0.5">{g.composition}</p>
          </div>
        )}

        {g.concept && (
          <pre className="rounded-lg bg-black/30 border border-white/5 px-3 py-2.5 text-xs text-white/70 leading-relaxed whitespace-pre-wrap font-sans">
            {g.concept}
          </pre>
        )}

        {/* "언제 사냐"가 제일 먼저 궁금한 질문인데 지금까지 어디에도 안 적혀 있었다.
            원전이 말하는 시점과 우리 실측을 분리해서 적는다 — 둘이 자주 어긋난다. */}
        {g.buy && (
          <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/[0.07] px-3 py-2.5">
            <span className="text-xs font-semibold text-emerald-300">언제 사는가</span>
            <pre className="mt-1 text-xs text-white/75 leading-relaxed whitespace-pre-wrap font-sans">
              {g.buy}
            </pre>
          </div>
        )}

        {g.conditions && (
          <div className="rounded-lg border border-white/10 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-white/5 text-xs text-white/40">
                  <th className="px-3 py-2 text-left font-medium">조건</th>
                  <th className="px-3 py-2 text-left font-medium">지표</th>
                  <th className="px-3 py-2 text-left font-medium">기준</th>
                </tr>
              </thead>
              <tbody>
                {g.conditions.map((r) => (
                  <tr key={r.cond} className="border-t border-white/5">
                    <td className="px-3 py-2 text-white/80">{r.cond}</td>
                    <td className="px-3 py-2 font-mono text-xs text-cyan-300/80">{r.ind}</td>
                    <td className="px-3 py-2 text-white/60 text-xs">{r.crit}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {g.scoring && (
          <div>
            <span className="text-xs text-white/40">점수 배분</span>
            <p className="text-xs text-white/70 mt-0.5 font-mono">{g.scoring}</p>
          </div>
        )}

        <div className="flex flex-wrap gap-x-6 gap-y-1 text-xs">
          {g.period && (
            <span className="text-white/50">
              적합 기간 <span className="text-white/80">{g.period}</span>
            </span>
          )}
          {g.note && <span className="text-amber-400/80">⚠️ {g.note}</span>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
