/**
 * Cầu nối token → Cytoscape.
 *
 * Cytoscape nhận chuỗi màu thô, nên adapter này quy đổi token thành đúng những
 * giá trị stylesheet cần. Nền tint của đỉnh rủi ro là hằng số đặt tên chứ không
 * còn là mã hex nằm giữa file stylesheet: chúng là màu ngữ nghĩa trộn với nền
 * panel, và phải đổi cùng nhau nếu bảng màu đổi.
 */

import { toneColor } from "../semantic";
import { ink, line, surface } from "../tokens";

export const cytoscapeTheme = {
  node: {
    fill: surface.elev,
    border: line.strong,
    label: ink.mid,
    labelActive: ink.hi,
    /** Nền đỉnh mức "đáng ngờ" — hổ phách pha rất tối, đủ để đọc là một khối màu. */
    fillWarn: "#221B0E",
    /** Nền đỉnh mức "nghiêm trọng". */
    fillCrit: "#2A1116",
    /** Nền đỉnh đang chọn — teal pha tối, cùng họ với `primary.soft` của CSS. */
    fillSelected: "#0C2620",
    fillMuted: surface.sunken,
    cluster: surface.panel,
    clusterParent: surface.side,
  },
  edge: {
    base: line.base,
    /** Cạnh dòng tiền nổi hơn cạnh cấu trúc một bậc. */
    money: "#2B4358",
    labelBackground: surface.app,
    gap: ink.dim,
  },
  tone: {
    warn: toneColor("warn"),
    crit: toneColor("risk"),
    selected: toneColor("primary"),
    muted: ink.dim,
  },
  font: {
    sans: "Geist, Inter, system-ui, sans-serif",
    mono: "JetBrains Mono, ui-monospace, monospace",
  },
  /** Khớp với `duration.fast` — phản hồi tương tác, không phải chuyển layout. */
  transitionMs: 140,
} as const;
