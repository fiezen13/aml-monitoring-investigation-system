/**
 * Cầu nối token → React Flow (đồ thị gọn của một vụ việc, `/network/:caseId`).
 *
 * React Flow style bằng object inline nên adapter trả về đúng những object đó.
 * Trước đây trang tự viết `#EF4444`, `#00B2A9`, `#F1F5F9` — ba màu không nằm
 * trong bảng màu nào của hệ thống, và màu đỏ ấy khác màu đỏ rủi ro thật sự.
 */

import { toneColor } from "../semantic";
import { ink, line, surface } from "../tokens";

export const reactFlowTheme = {
  background: surface.app,
  grid: line.faint,
  node: {
    fill: surface.panel,
    border: line.strong,
    text: ink.hi,
    subtext: ink.low,
  },
  edge: {
    base: line.strong,
    label: ink.mid,
    labelBackground: surface.raised,
  },
  /** Thực thể trung tâm của vụ việc — dùng accent vì nó là "đang xem". */
  focus: toneColor("primary"),
  risk: toneColor("risk"),
} as const;
