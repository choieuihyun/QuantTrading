"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart2, LayoutDashboard, History, ListChecks, Briefcase } from "lucide-react";

const NAV = [
  { href: "/",          label: "대시보드",  icon: LayoutDashboard },
  { href: "/backtest",  label: "백테스트",  icon: BarChart2 },
  { href: "/track",     label: "성적표",     icon: ListChecks },
  { href: "/portfolio", label: "가상 매매",  icon: Briefcase },
  { href: "/replay",    label: "3년치 통계",  icon: History },
];

export function Header({ runAt }: { runAt?: string }) {
  const pathname = usePathname();

  return (
    <header className="border-b border-white/10 px-6 py-3 flex items-center justify-between sticky top-0 z-50 bg-[#080a0f]/95 backdrop-blur">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-xs font-bold text-white">Q</div>
          <span className="font-semibold tracking-tight text-white">QuantTrading</span>
        </div>

        <nav className="flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  active
                    ? "bg-white/10 text-white"
                    : "text-white/50 hover:text-white/80 hover:bg-white/5"
                }`}
              >
                <Icon size={13} />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="text-xs text-white/30">
        {runAt ? `마지막 업데이트: ${runAt}` : ""}
      </div>
    </header>
  );
}
