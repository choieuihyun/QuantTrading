"use client";
import { motion } from "framer-motion";

export function ScoreBar({ score }: { score: number }) {
  const color =
    score >= 80 ? "bg-emerald-500" :
    score >= 60 ? "bg-amber-400" :
    "bg-blue-400";

  return (
    <div className="flex items-center gap-2">
      <div className="w-24 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${color}`}
          initial={{ width: 0 }}
          animate={{ width: `${score}%` }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      </div>
      <span className="text-xs font-mono text-white/80">{score.toFixed(0)}</span>
    </div>
  );
}
