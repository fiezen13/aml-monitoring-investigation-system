/**
 * Cầu nối token → Recharts.
 *
 * Recharts mặc định vẽ lưới xám sáng, trục đen và tooltip nền trắng — trong một
 * console tối, một biểu đồ Recharts chưa chỉnh trông như dán từ dự án khác vào.
 * Ba object dưới đây trải thẳng vào props của `CartesianGrid`, `XAxis`/`YAxis`
 * và `Tooltip`.
 */

import { chartTheme } from "../visualization";

export const axisProps = {
  stroke: chartTheme.axis,
  tick: { fill: chartTheme.tick, fontSize: 10 },
  tickLine: false,
  axisLine: { stroke: chartTheme.axis },
} as const;
