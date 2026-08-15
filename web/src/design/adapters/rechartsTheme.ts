/**
 * Cầu nối token → Recharts.
 *
 * Recharts mặc định vẽ lưới xám sáng, trục đen và tooltip nền trắng — trong một
 * console tối, một biểu đồ Recharts chưa chỉnh trông như dán từ dự án khác vào.
 * Ba object dưới đây trải thẳng vào props của `CartesianGrid`, `XAxis`/`YAxis`
 * và `Tooltip`.
 */

import { chartTheme } from "../visualization";
import { radius } from "../tokens";

export const gridProps = {
  stroke: chartTheme.grid,
  strokeDasharray: "2 4",
  vertical: false,
} as const;

export const axisProps = {
  stroke: chartTheme.axis,
  tick: { fill: chartTheme.tick, fontSize: 10 },
  tickLine: false,
  axisLine: { stroke: chartTheme.axis },
} as const;

/**
 * Tooltip phải trông đúng như popover của app: cùng nền `raised`, cùng viền,
 * cùng bo góc. Đây là chỗ dễ lộ nhất khi một hệ thống được ghép từ nhiều nguồn.
 */
export const tooltipProps = {
  cursor: { fill: "rgba(32, 199, 167, 0.06)" },
  contentStyle: {
    background: chartTheme.tooltip.background,
    border: `1px solid ${chartTheme.tooltip.border}`,
    borderRadius: radius.control,
    padding: "8px 10px",
    fontSize: 11,
    lineHeight: 1.45,
    boxShadow: "0 12px 28px -12px rgba(0,0,0,0.65)",
  },
  labelStyle: { color: chartTheme.tooltip.muted, marginBottom: 4, fontSize: 10 },
  itemStyle: { color: chartTheme.tooltip.text, padding: 0 },
} as const;

/** Thời lượng animation dùng chung — khớp `duration.normal` của hệ chuyển động. */
export const chartAnimationMs = chartTheme.durationMs;
