import type { Config } from "tailwindcss";

import { accent, elevation, hue, ink, layer, line, radius, surface } from "./src/design/tokens";

/**
 * Cấu hình Tailwind của F7 Console.
 *
 * File này KHÔNG còn tự khai báo giá trị màu. Mọi thứ đọc từ
 * `src/design/tokens.ts` — trước đây bảng màu tồn tại hai bản (một ở đây cho
 * class CSS, một ở `palette.ts` cho canvas) và hai bản đã bắt đầu trôi khỏi
 * nhau. Một nguồn, hai đích.
 *
 * Tên token đặt theo vai trò chứ không theo màu, để đổi tông về sau không phải
 * sửa từng chỗ dùng.
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: surface.app,
        side: surface.side,
        panel: surface.panel,
        elev: surface.elev,
        raised: surface.raised,
        sunken: surface.sunken,
        scrim: surface.scrim,

        primary: {
          DEFAULT: accent.base,
          hover: accent.hover,
          press: accent.press,
          soft: accent.soft,
          softer: accent.softer,
          line: accent.line,
          on: accent.on,
        },

        line: {
          faint: line.faint,
          soft: line.soft,
          DEFAULT: line.base,
          strong: line.strong,
          emphasis: line.emphasis,
        },

        ink: {
          hi: ink.hi,
          mid: ink.mid,
          soft: ink.soft,
          low: ink.low,
          dim: ink.dim,
        },

        risk: { DEFAULT: hue.risk.base, soft: hue.risk.soft },
        warn: { DEFAULT: hue.warn.base, soft: hue.warn.soft },
        ok: { DEFAULT: hue.ok.base, soft: hue.ok.soft },
        info: { DEFAULT: hue.info.base, soft: hue.info.soft },
        agent: { DEFAULT: hue.agent.base, soft: hue.agent.soft },
        token: { DEFAULT: hue.token.base, soft: hue.token.soft },
      },

      fontFamily: {
        sans: ["Geist", "Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },

      /**
       * Thang chữ.
       *
       * Hai bộ tên cùng trỏ vào một thang: bộ theo vai trò (`micro`…`h1`) dành
       * cho code mới, bộ theo kích cỡ (`3xs`…`4xl`) giữ lại để các trang chưa
       * migrate không gãy. Bộ cũ được chỉnh lại cho khớp thang mới thay vì giữ
       * nguyên các giá trị lẻ 11.5 / 12.5 / 13.5px trước đây.
       */
      fontSize: {
        micro: ["10px", "14px"],
        meta: ["11px", "15px"],
        data: ["12px", "16px"],
        body: ["13px", "18px"],
        "body-lg": ["14px", "20px"],
        h3: ["16px", "22px"],
        h2: ["20px", "27px"],
        h1: ["24px", "31px"],

        "3xs": ["10px", "14px"],
        "2xs": ["11px", "15px"],
        xs: ["12px", "16px"],
        sm: ["12px", "16px"],
        base: ["13px", "18px"],
        md: ["13px", "18px"],
        lg: ["14px", "20px"],
        xl: ["16px", "22px"],
        "2xl": ["16px", "22px"],
        "3xl": ["20px", "27px"],
        "4xl": ["24px", "31px"],
      },

      borderRadius: {
        panel: radius.panel,
        control: radius.control,
        chip: radius.chip,
        sm: radius.sm,
      },

      boxShadow: {
        popover: elevation.popover,
        modal: elevation.modal,
        focus: elevation.focus,
      },

      zIndex: {
        hud: String(layer.overlayHud),
        sticky: String(layer.sticky),
        dropdown: String(layer.dropdown),
        drawer: String(layer.drawer),
        modal: String(layer.modal),
        toast: String(layer.toast),
      },

      keyframes: {
        // Nhịp đập của chỉ báo LIVE và các chấm trạng thái.
        fcPulse: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.3" } },
        // Chuyển màn hình: trôi lên 5px. Ngắn, không gây chờ đợi.
        fcUp: {
          from: { opacity: "0", transform: "translateY(5px)" },
          to: { opacity: "1", transform: "none" },
        },
        // Cảnh báo mới vào bảng: nền loé lên rồi tắt. Một lần, không lặp.
        fcFlash: {
          "0%": { backgroundColor: "rgba(244, 91, 105, 0.14)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        pulse: "fcPulse 2.2s infinite",
        up: "fcUp 0.25s ease",
        flash: "fcFlash 1.1s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
