/**
 * Chủ đề dùng chung cho CẢ HAI bộ dựng bản đồ.
 *
 * Đây là điểm mấu chốt của yêu cầu "2D và 3D phải thuộc cùng một sản phẩm".
 * Trước đây MapLibre có bảng màu riêng (`BASEMAP` với ba mã hex tự đặt) còn
 * Cesium dùng ảnh vệ tinh đã hạ sáng — nhìn cạnh nhau là hai ứng dụng khác
 * nhau. Giờ cả hai đọc cùng một chỗ; khác biệt chỉ còn là phép chiếu.
 *
 * Quy ước màu bề mặt bản đồ:
 *
 *   đại dương  → tối hơn nền trang một bậc (nước là khoảng trống)
 *   đất liền   → cùng họ với `panel` nhưng ngả lạnh (đất là bối cảnh)
 *   đường biên → `line.strong` ngả lạnh, chỉ đủ để đọc hình thái
 *
 * Tất cả tín hiệu AML (node, hành lang, vùng chọn) nằm trên ba tầng ấy và mới
 * là thứ được phép bão hoà.
 */

import { toneColor } from "../semantic";
import type { Severity } from "../risk";
import { accent, ink, surface } from "../tokens";
import { CHANNEL } from "../visualization";

/** Bề mặt cơ sở — dùng cho basemap 2D và cho màu nền/quả cầu của Cesium. */
export const mapSurface = {
  ocean: "#06111D",
  land: "#122334",
  border: "#294356",
  /** Nền ngoài quả cầu ở chế độ 3D — chính là nền trang, để không có vành sáng. */
  space: surface.app,
  /** Màu cơ sở của quả cầu khi ảnh bề mặt chưa nạp xong. */
  globeBase: "#08111C",
  label: ink.mid,
  labelMuted: ink.dim,
} as const;

/**
 * Hạ sáng ảnh bề mặt của Cesium.
 *
 * Ảnh vệ tinh nguyên bản sáng và rực màu tới mức cung giao dịch chìm nghỉm; bộ
 * số này kéo nó về gần đúng độ sáng của `mapSurface.land` để 3D và 2D có cùng
 * cảm giác nền.
 */
export const imageryTone = {
  brightness: 0.55,
  saturation: 0.42,
  contrast: 1.12,
  gamma: 1.15,
} as const;

/** Màu theo mức độ rủi ro của hành lang — dùng chung cho cung 3D và đường 2D. */
export const routeColor: Record<Severity, string> = {
  crit: toneColor("risk"),
  warn: toneColor("warn"),
  // Hành lang bình thường mang màu thông tin chứ không xanh lá: xanh lá trên
  // bản đồ dễ đọc nhầm thành địa hình.
  ok: toneColor("info"),
};

/** Màu theo kênh — chỉ dùng khi mức độ rủi ro chưa nói gì (không nghiêm trọng). */
export const channelColor = CHANNEL;

/** Vùng chọn và hover. Teal giữ đúng nghĩa "đang chọn" như phần còn lại của app. */
export const mapSelection = {
  selected: accent.base,
  selectedGlow: "rgba(32, 199, 167, 0.35)",
  hover: ink.hi,
} as const;

/** Bầu khí quyển của quả cầu — rất nhạt, chỉ để tách rìa Trái Đất khỏi nền. */
export const atmosphere = {
  hueShift: -0.06,
  saturationShift: -0.5,
  brightnessShift: -0.32,
} as const;
