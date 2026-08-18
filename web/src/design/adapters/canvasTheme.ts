/**
 * Cầu nối token → engine canvas tự viết (`src/vendor/fc/`).
 *
 * Engine ấy là JavaScript thuần, nạp qua custom element và không import gì từ
 * cây React, nên không thể `import` token trực tiếp. Cách nối duy nhất không
 * phải viết lại nó là biến CSS: hàm dưới đây in token ra `:root`, engine đọc
 * bằng `getComputedStyle` và vẫn giữ giá trị dự phòng nếu biến chưa có.
 *
 * Gọi một lần lúc khởi động ứng dụng, trước khi component canvas đầu tiên
 * dựng — xem `src/main.tsx`.
 */

import { hue, ink, line, surface } from "../tokens";
import { toneColor } from "../semantic";

const VARS: Record<string, string> = {
  "--fc-grid": "rgba(133,173,209,0.06)",
  "--fc-txt": ink.soft,
  "--fc-mut": ink.low,
  "--fc-hi": ink.hi,
  "--fc-accent": toneColor("primary"),
  "--fc-blue": hue.info.base,
  "--fc-amber": hue.warn.base,
  "--fc-red": hue.risk.base,
  "--fc-green": hue.ok.base,
  "--fc-purple": hue.agent.base,
  "--fc-app": surface.app,
  "--fc-sunken": surface.sunken,
  "--fc-raised": surface.raised,
  "--fc-line": line.strong,
};

export function installCanvasTheme(root: HTMLElement = document.documentElement): void {
  for (const [name, value] of Object.entries(VARS)) {
    root.style.setProperty(name, value);
  }
}
