"use client";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from "recharts";
import type { Stock } from "@/lib/types";
import { MetricBadge } from "./MetricBadge";

interface Props {
  stock: Stock | null;
  onClose: () => void;
}

export function StockDetailModal({ stock, onClose }: Props) {
  if (!stock) return null;

  const radarData = [
    { subject: "점수",     value: stock.score },
    { subject: "RSI",      value: Math.min(stock.rsi, 100) },
    { subject: "모멘텀",   value: Math.min(stock.momentum_3m * 200, 100) },
    { subject: "거래량",   value: Math.min(stock.vol_ratio * 25, 100) },
    { subject: "MA정렬",   value: stock.full_aligned ? 100 : stock.ma20 > stock.ma60 ? 60 : 30 },
  ];

  const maAligned = stock.ma5 > stock.ma20 && stock.ma20 > stock.ma60;

  return (
    <Dialog open={!!stock} onOpenChange={onClose}>
      <DialogContent className="bg-[#0f1117] border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-3">
            <span className="text-xl font-bold">{stock.name}</span>
            <span className="text-sm text-white/40 font-mono">{stock.ticker}</span>
            <span className="text-xs px-2 py-0.5 bg-white/10 rounded">{stock.market}</span>
          </DialogTitle>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-6 mt-2">
          {/* 차트 */}
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarData}>
                <PolarGrid stroke="rgba(255,255,255,0.1)" />
                <PolarAngleAxis dataKey="subject" tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 11 }} />
                <Radar dataKey="value" stroke="#6366f1" fill="#6366f1" fillOpacity={0.3} />
                <Tooltip
                  contentStyle={{ background: "#1a1d27", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8 }}
                  labelStyle={{ color: "white" }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          {/* 지표 */}
          <div className="space-y-3">
            <div>
              <p className="text-xs text-white/40 mb-1.5">현재가 & 이평선</p>
              <div className="flex flex-wrap gap-1.5">
                <MetricBadge label="현재가" value={stock.price.toLocaleString()} neutral />
                <MetricBadge label="MA5"   value={stock.ma5.toLocaleString()} neutral />
                <MetricBadge label="MA20"  value={stock.ma20.toLocaleString()} neutral />
                <MetricBadge label="MA60"  value={stock.ma60.toLocaleString()} neutral />
                <MetricBadge label="MA120" value={stock.ma120.toLocaleString()} neutral />
              </div>
            </div>
            <div>
              <p className="text-xs text-white/40 mb-1.5">기술 지표</p>
              <div className="flex flex-wrap gap-1.5">
                <MetricBadge label="RSI"  value={stock.rsi.toFixed(1)} positive={stock.rsi >= 50 && stock.rsi <= 70} />
                <MetricBadge label="MACD" value={stock.macd.toFixed(2)} positive={stock.macd > 0} />
                <MetricBadge label="거래량배수" value={`${stock.vol_ratio}x`} positive={stock.vol_ratio >= 2} />
                <MetricBadge label="3M모멘텀" value={`${(stock.momentum_3m * 100).toFixed(1)}%`} positive={stock.momentum_3m > 0} />
              </div>
            </div>
            <div>
              <p className="text-xs text-white/40 mb-1.5">패턴 신호</p>
              <div className="flex flex-wrap gap-1.5">
                <MetricBadge label="정배열" value={maAligned ? "✓" : "✗"} positive={maAligned} />
                {stock.bb_squeeze !== undefined && (
                  <MetricBadge label="BB수축" value={stock.bb_squeeze ? "✓" : "✗"} positive={!!stock.bb_squeeze} />
                )}
                {stock.obv_rising !== undefined && (
                  <MetricBadge label="OBV↑" value={stock.obv_rising ? "✓" : "✗"} positive={!!stock.obv_rising} />
                )}
                {stock.pullback_pct !== undefined && (
                  <MetricBadge label="눌림목" value={`${(stock.pullback_pct * 100).toFixed(1)}%`} positive={!!stock.in_fib_zone} />
                )}
                {stock.in_fib_zone !== undefined && (
                  <MetricBadge label="피보나치" value={stock.in_fib_zone ? "구간內" : "구간外"} positive={!!stock.in_fib_zone} />
                )}
              </div>
            </div>
          </div>
        </div>

        <a
          href={`https://finance.naver.com/item/main.naver?code=${stock.ticker}`}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 text-xs text-indigo-400 hover:text-indigo-300 underline"
        >
          네이버 금융에서 차트 보기 →
        </a>
      </DialogContent>
    </Dialog>
  );
}
