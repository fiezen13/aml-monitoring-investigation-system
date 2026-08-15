import { motion } from "motion/react";
import { TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import { TONE, type Tone } from "../../design/semantic";
import { METRIC_VALUE, METRIC_VALUE_SM, TEXT } from "../../design/typography";
import { safeVariants, staggerItem, useReduced } from "../../design/motion";
import { AnimatedNumber } from "./AnimatedNumber";

/**
 * Thẻ chỉ số.
 *
 * Hợp nhất `fc/primitives.KpiCard` (số mono lớn, không icon) và
 * `common/KPIStatCard` (có icon, xu hướng, sparkline). Giữ toàn bộ khả năng của
 * bản sau nhưng bỏ sparkline: nó vẽ bằng Recharts trong một thẻ cao 76px, tức
 * là kéo cả một thư viện biểu đồ vào để hiện tám điểm dữ liệu không có trục,
 * không nhãn và không đọc được giá trị.
 *
 * `tone` chỉ tô con số, không tô cả thẻ — sáu thẻ KPI mà mỗi thẻ một nền màu
 * thì hàng đầu trang biến thành một dải cầu vồng và không cái nào nổi lên nữa.
 */

interface Props {
  label: string;
  /** Truyền số để có nội suy khi dữ liệu đổi; truyền chuỗi cho giá trị không phải số. */
  value: number | string;
  format?: (value: number) => string;
  tone?: Tone;
  icon?: ReactNode;
  /** Dòng ngữ cảnh dưới số liệu: nguồn, tỷ lệ, trạng thái. */
  note?: ReactNode;
  trend?: { value: string; direction: "up" | "down"; tone: Tone };
  size?: "md" | "sm";
  onClick?: () => void;
  className?: string;
}

export function MetricCard({
  label,
  value,
  format,
  tone = "neutral",
  icon,
  note,
  trend,
  size = "md",
  onClick,
  className = "",
}: Props) {
  const reduced = useReduced();
  const color = tone === "neutral" ? undefined : TONE[tone].base;
  const Tag = onClick ? motion.button : motion.div;

  return (
    <Tag
      variants={safeVariants(staggerItem, reduced)}
      onClick={onClick}
      type={onClick ? "button" : undefined}
      className={`rounded-panel bg-panel text-left transition-colors ${
        size === "sm" ? "px-3 py-2.5" : "px-4 py-3.5"
      } ${onClick ? "cursor-pointer hover:bg-elev" : ""} ${className}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className={`truncate-1 ${TEXT.eyebrow}`}>{label}</span>
        {icon && <span className="flex-none text-ink-dim">{icon}</span>}
      </div>

      <div
        className={`mt-1.5 truncate-1 ${size === "sm" ? METRIC_VALUE_SM : METRIC_VALUE}`}
        style={color ? { color } : undefined}
      >
        {typeof value === "number" ? <AnimatedNumber value={value} format={format} /> : value}
      </div>

      {trend && (
        <div className={`mt-1.5 flex items-center gap-1 text-meta font-medium ${TONE[trend.tone].textClass}`}>
          {trend.direction === "up" ? <TrendingUp size={12} aria-hidden /> : <TrendingDown size={12} aria-hidden />}
          {trend.value}
        </div>
      )}

      {note != null && <div className="mt-1.5 text-meta text-ink-low">{note}</div>}
    </Tag>
  );
}

/** Ô số liệu nhỏ cho sidebar và inspector — cùng ngôn ngữ, ít không gian hơn. */
export function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
  className = "",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  className?: string;
}) {
  const color = tone === "neutral" ? undefined : TONE[tone].base;
  return (
    <div className={`min-w-0 rounded-panel bg-panel px-2.5 py-2 ${className}`}>
      <div className="truncate-1 text-meta text-ink-low">{label}</div>
      <div className={`truncate-1 mt-0.5 ${METRIC_VALUE_SM}`} style={color ? { color } : undefined}>
        {value}
      </div>
      {sub != null && <div className="truncate-1 text-micro text-ink-dim">{sub}</div>}
    </div>
  );
}
