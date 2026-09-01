/**
 * Bảng màu cho phần dựng hình dữ liệu.
 *
 * Bảy engine cùng vẽ trong console này — canvas tự viết, Recharts, Cytoscape,
 * React Flow, MapLibre, Cesium, Three — và trước đây mỗi engine mang một bảng
 * màu riêng. Tất cả phải đi qua file này, rồi qua adapter tương ứng trong
 * `design/adapters/`.
 *
 * Luật ưu tiên: màu rủi ro luôn thắng màu phân loại. Một hành lang nghiêm trọng
 * phải đỏ dù nó thuộc kênh nào; màu kênh chỉ nói "loại gì" khi rủi ro chưa nói
 * gì cả.
 */

import { hue, ink, line, surface } from "./tokens";

/**
 * Thứ tự màu mặc định cho series không chỉ định màu riêng.
 *
 * Mở đầu bằng xanh dương chứ không phải teal: teal là màu của "đang chọn", và
 * một biểu đồ mà series đầu tiên luôn teal thì tín hiệu đó mất nghĩa.
 */
export const SERIES = [
  hue.info.base,
  hue.agent.base,
  hue.ok.base,
  hue.warn.base,
  hue.risk.base,
  hue.token.base,
] as const;

/**
 * Kênh dòng tiền — dùng chung bởi bản đồ, đồ thị mạng lưới và chú giải.
 *
 * Không kênh nào lấy màu accent: trên bản đồ, teal dành riêng cho thực thể đang
 * được chọn, và nếu P2P cũng teal thì không phân biệt được "kênh P2P" với "hành
 * lang tôi vừa bấm".
 */
export const CHANNEL: Record<string, string> = {
  bank: hue.info.base,
  p2p: "#38BDF8",
  vasp: hue.agent.base,
  chain: hue.ok.base,
  gamb: hue.warn.base,
  proj: hue.token.base,
};

export const CHANNEL_LABEL: Record<string, string> = {
  bank: "Ngân hàng",
  p2p: "P2P",
  vasp: "VASP",
  chain: "Cầu nối chuỗi",
  gamb: "Cá cược",
  proj: "Tài sản số",
};

/**
 * Chủ đề chung cho mọi biểu đồ: lưới, trục, nhãn, tooltip, trạng thái rỗng.
 * Adapter của từng thư viện đọc từ đây thay vì tự đặt.
 */
export const chartTheme = {
  grid: line.faint,
  axis: line.base,
  tick: ink.dim,
  label: ink.low,
  background: "transparent",
  tooltip: {
    background: surface.raised,
    border: line.strong,
    text: ink.hi,
    muted: ink.low,
  },
  /** Thời lượng animation của biểu đồ, tính bằng mili giây (API của Recharts). */
  durationMs: 220,
} as const;

/** Đồ thị mạng lưới: màu theo loại thực thể. */
export const ENTITY_COLOR: Record<string, string> = {
  person: "#38BDF8",
  company: hue.info.base,
  account: ink.mid,
  bank: hue.info.base,
  vasp: hue.agent.base,
  wallet: hue.token.base,
  project: hue.token.base,
  unknown: ink.dim,
};
