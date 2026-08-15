/**
 * Lớp tương thích cho bảng màu cũ.
 *
 * `palette.ts` từng là bản sao chép tay của `tailwind.config.js`. Nay nó chỉ
 * còn là một mặt tiền: giá trị đến từ `tokens.ts`, ngữ nghĩa đến từ
 * `semantic.ts` và `risk.ts`.
 *
 * File này tồn tại để hơn hai chục module đang `import { C } from
 * "../design/palette"` không phải sửa cùng lúc. Code mới KHÔNG dùng `C` — dùng
 * `toneColor()` cho màu ngữ nghĩa, `getRiskColor()` cho rủi ro, và
 * `visualization.ts` cho phần dựng hình.
 *
 * @deprecated Chuyển dần sang `design/semantic`, `design/risk`, `design/tokens`.
 */

import { accent, hue, ink, line, surface } from "./tokens";

export { SERIES, CHANNEL, CHANNEL_LABEL } from "./visualization";
export { deltaColor, getRiskColor as riskColor, getRiskShortLabel as riskLabel } from "./risk";

export const C = {
  app: surface.app,
  side: surface.side,
  panel: surface.panel,
  elev: surface.elev,
  raised: surface.raised,
  sunken: surface.sunken,

  primary: accent.base,
  primaryHi: accent.hover,

  inkHi: ink.hi,
  inkMid: ink.mid,
  inkSoft: ink.soft,
  inkLow: ink.low,
  inkDim: ink.dim,

  risk: hue.risk.base,
  riskSoft: hue.risk.soft,
  warn: hue.warn.base,
  warnSoft: hue.warn.soft,
  ok: hue.ok.base,
  okSoft: hue.ok.soft,
  info: hue.info.base,
  infoSoft: hue.info.soft,
  agent: hue.agent.base,
  agentSoft: hue.agent.soft,
  token: hue.token.base,

  grid: line.faint,
  line: line.base,
  lineStrong: line.strong,
} as const;
