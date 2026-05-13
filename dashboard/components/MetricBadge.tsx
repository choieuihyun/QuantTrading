"use client";

interface Props {
  label: string;
  value: string | number;
  positive?: boolean;
  neutral?: boolean;
}

export function MetricBadge({ label, value, positive, neutral }: Props) {
  const color = neutral
    ? "bg-white/5 text-white/60"
    : positive
    ? "bg-emerald-500/20 text-emerald-400"
    : "bg-rose-500/20 text-rose-400";

  return (
    <div className={`inline-flex flex-col items-center px-2 py-1 rounded-md ${color}`}>
      <span className="text-[10px] uppercase tracking-wider opacity-70">{label}</span>
      <span className="text-xs font-mono font-semibold">{value}</span>
    </div>
  );
}
