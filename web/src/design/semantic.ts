/**
 * Tầng ngữ nghĩa: "màu này nói điều gì", tách khỏi "màu này là mã hex nào".
 *
 * Trước đây mỗi trang tự chọn màu cho badge, chip và nhãn trạng thái, nên cùng
 * một khái niệm hiện ra ba kiểu khác nhau ở ba màn hình (và ở AlertsPage còn là
 * ba mã hex Tailwind mặc định không có trong bảng màu của hệ thống). Từ đây,
 * component chỉ chọn `tone`; màu, viền và nền do file này quyết định.
 */

import { hue, ink, accent } from "./tokens";

/**
 * Bảng ngữ nghĩa của console.
 *
 * - `neutral`  — không mang phán xét, dùng cho metadata và trạng thái trung tính
 * - `primary`  — đang chọn / hành động chính (teal, không dùng cho gì khác)
 * - `info`     — thông tin, tham chiếu, bộ phát hiện dựa trên đồ thị
 * - `ok`       — khoẻ mạnh, đã đóng, dưới ngưỡng
 * - `warn`     — cần chú ý, đang theo dõi
 * - `risk`     — nghiêm trọng, quá hạn, thất bại
 * - `agent`    — hoạt động của tác tử AI và VASP
 * - `token`    — kênh tài sản số / dự án
 */
export type Tone = "neutral" | "primary" | "info" | "ok" | "warn" | "risk" | "agent" | "token";

interface ToneSpec {
  /** Màu đặc: viền, chấm, thanh, series biểu đồ. */
  base: string;
  /** Bản nhạt hơn dành cho chữ đặt trên nền tint. */
  soft: string;
  /** Bộ class Tailwind cho khối có nền tint (badge, chip, callout). */
  surfaceClass: string;
  /** Class chỉ đổi màu chữ. */
  textClass: string;
  /** Class chỉ đổi màu viền. */
  borderClass: string;
}

export const TONE: Record<Tone, ToneSpec> = {
  neutral: {
    base: ink.low,
    soft: ink.mid,
    surfaceClass: "border-line-strong bg-elev/60 text-ink-mid",
    textClass: "text-ink-mid",
    borderClass: "border-line-strong",
  },
  primary: {
    base: accent.base,
    soft: accent.hover,
    surfaceClass: "border-primary/30 bg-primary-soft text-primary",
    textClass: "text-primary",
    borderClass: "border-primary/40",
  },
  info: {
    base: hue.info.base,
    soft: hue.info.soft,
    surfaceClass: "border-info/30 bg-info/10 text-info-soft",
    textClass: "text-info-soft",
    borderClass: "border-info/40",
  },
  ok: {
    base: hue.ok.base,
    soft: hue.ok.soft,
    surfaceClass: "border-ok/30 bg-ok/10 text-ok-soft",
    textClass: "text-ok-soft",
    borderClass: "border-ok/40",
  },
  warn: {
    base: hue.warn.base,
    soft: hue.warn.soft,
    surfaceClass: "border-warn/30 bg-warn/10 text-warn-soft",
    textClass: "text-warn-soft",
    borderClass: "border-warn/40",
  },
  risk: {
    base: hue.risk.base,
    soft: hue.risk.soft,
    surfaceClass: "border-risk/30 bg-risk/10 text-risk-soft",
    textClass: "text-risk-soft",
    borderClass: "border-risk/40",
  },
  agent: {
    base: hue.agent.base,
    soft: hue.agent.soft,
    surfaceClass: "border-agent/30 bg-agent/10 text-agent-soft",
    textClass: "text-agent-soft",
    borderClass: "border-agent/40",
  },
  token: {
    base: hue.token.base,
    soft: hue.token.soft,
    surfaceClass: "border-token/30 bg-token/10 text-token-soft",
    textClass: "text-token-soft",
    borderClass: "border-token/40",
  },
};

/** Màu đặc của một tone — dùng cho canvas, SVG và spec biểu đồ. */
export function toneColor(tone: Tone): string {
  return TONE[tone].base;
}

/** Bản nhạt của một tone — dùng cho chữ trên nền tint. */
export function toneSoft(tone: Tone): string {
  return TONE[tone].soft;
}

/**
 * Ngữ nghĩa của bộ phát hiện. Đặt ở đây thay vì trong từng trang vì cùng một
 * `detector` xuất hiện ở Trung tâm cảnh báo, Tổng quan và Chi tiết cảnh báo.
 */
export const DETECTOR_TONE: Record<string, Tone> = {
  rule: "neutral",
  ml: "primary",
  graph: "info",
  agent: "agent",
};

/** Ngữ nghĩa của trạng thái cảnh báo. */
export const ALERT_STATUS_TONE: Record<string, Tone> = {
  open: "risk",
  grouped: "warn",
  triaged: "warn",
  closed: "ok",
};

/** Ngữ nghĩa của trạng thái vụ việc. */
export const CASE_STATUS_TONE: Record<string, Tone> = {
  open: "warn",
  investigating: "info",
  escalated: "risk",
  filed: "agent",
  closed: "ok",
};

/** Ngữ nghĩa của trạng thái phê duyệt SAR. */
export const APPROVAL_STATUS_TONE: Record<string, Tone> = {
  draft: "neutral",
  pending: "warn",
  pending_approval: "warn",
  approved: "ok",
  rejected: "risk",
  filed: "info",
};
