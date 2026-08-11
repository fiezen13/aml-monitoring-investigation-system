import { TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";
import { Line, LineChart, ResponsiveContainer } from "recharts";

interface KPIStatCardProps {
  label: string;
  value: string;
  icon?: ReactNode;
  trend?: { value: string; direction: "up" | "down"; tone: "good" | "bad" | "neutral" };
  note?: string;
  spark?: number[];
  sparkColor?: string;
}

/** KPI card đầu trang — số lớn tabular, xu hướng kèm icon, sparkline nhỏ. */
export function KPIStatCard({
  label,
  value,
  icon,
  trend,
  note,
  spark,
  sparkColor = "#00B2A9",
}: KPIStatCardProps) {
  const trendColor =
    trend?.tone === "good"
      ? "text-ok"
      : trend?.tone === "bad"
        ? "text-risk"
        : "text-ink-mid";
  return (
    <div className="rounded-panel border border-line bg-panel p-4">
      <div className="flex items-start justify-between">
        <span className="text-2xs font-semibold uppercase tracking-wider text-ink-mid">
          {label}
        </span>
        {icon && <span className="text-ink-mid">{icon}</span>}
      </div>
      <div className="mt-2 flex items-end justify-between gap-2">
        <div>
          <div className="tabular text-[26px] font-bold leading-none text-ink-hi">
            {value}
          </div>
          {trend && (
            <div
              className={`mt-1.5 flex items-center gap-1 text-2xs font-medium ${trendColor}`}
            >
              {trend.direction === "up" ? (
                <TrendingUp size={12} aria-hidden />
              ) : (
                <TrendingDown size={12} aria-hidden />
              )}
              {trend.value}
            </div>
          )}
          {note && <div className="mt-1 text-2xs text-ink-low">{note}</div>}
        </div>
        {spark && (
          <div className="h-8 w-20">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={spark.map((y, i) => ({ i, y }))}>
                <Line
                  type="monotone"
                  dataKey="y"
                  stroke={sparkColor}
                  strokeWidth={1.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
