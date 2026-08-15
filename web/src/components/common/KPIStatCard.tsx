import type { ReactNode } from "react";

import type { Tone } from "../../design/semantic";
import { MetricCard } from "../ui/MetricCard";

/**
 * Lớp tương thích — thẻ chỉ số thật nằm ở `components/ui/MetricCard`.
 *
 * Sparkline bị bỏ: nó kéo cả Recharts vào một thẻ cao 76px để vẽ tám điểm dữ
 * liệu không có trục, không nhãn và không đọc được giá trị. Prop vẫn nhận để
 * chỗ gọi không gãy, nhưng không dựng gì.
 *
 * @deprecated Import `MetricCard` từ `components/ui`.
 */

interface KPIStatCardProps {
  label: string;
  value: string;
  icon?: ReactNode;
  trend?: { value: string; direction: "up" | "down"; tone: "good" | "bad" | "neutral" };
  note?: string;
  spark?: number[];
  sparkColor?: string;
}

const TREND_TONE: Record<"good" | "bad" | "neutral", Tone> = {
  good: "ok",
  bad: "risk",
  neutral: "neutral",
};

export function KPIStatCard({ label, value, icon, trend, note }: KPIStatCardProps) {
  return (
    <MetricCard
      label={label}
      value={value}
      icon={icon}
      note={note}
      trend={trend ? { value: trend.value, direction: trend.direction, tone: TREND_TONE[trend.tone] } : undefined}
    />
  );
}
