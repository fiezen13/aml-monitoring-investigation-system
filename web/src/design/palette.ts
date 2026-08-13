// Màu dùng cho canvas, SVG và spec biểu đồ.
//
// Tailwind chỉ sinh ra class CSS; canvas thì cần chuỗi màu thật. Hai nơi phải
// khớp nhau, nên bảng này là bản sao có chủ đích của `tailwind.config.js` —
// sửa một bên thì sửa cả bên kia.

export const C = {
  app: "#050B12",
  side: "#07111C",
  panel: "#0D1C2A",
  elev: "#112538",
  sunken: "#0A1724",

  primary: "#12D6C5",
  primaryHi: "#5FE8DB",

  inkHi: "#E6F0F8",
  inkMid: "#B9C9D6",
  inkSoft: "#91A4B5",
  inkLow: "#607487",
  inkDim: "#4A5D70",

  risk: "#FF4D61",
  riskSoft: "#FF6B7C",
  warn: "#F5A524",
  warnSoft: "#F5C97A",
  ok: "#2DD4A7",
  okSoft: "#8FE8DF",
  info: "#3185FF",
  infoSoft: "#6FB0FF",
  agent: "#A78BFA",
  agentSoft: "#C9B8FC",
  token: "#FF8A5C",

  grid: "rgba(133,173,209,0.10)",
  line: "rgba(133,173,209,0.14)",
} as const;

/** Thứ tự màu mặc định cho các series không chỉ định màu riêng. */
export const SERIES = [C.primary, C.info, C.warn, C.risk, C.agent, C.ok];

/** Màu theo kênh dòng tiền — dùng chung bởi world map, network graph và chú giải. */
export const CHANNEL: Record<string, string> = {
  bank: C.info,
  p2p: C.primary,
  vasp: C.agent,
  chain: C.ok,
  gamb: C.warn,
  proj: C.token,
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
 * Màu theo điểm rủi ro 0–100.
 *
 * Ba ngưỡng này lặp lại ở mọi màn hình (bảng alert, thẻ case, inspector), nên
 * chúng phải đến từ một chỗ duy nhất — nếu không, cùng một điểm số sẽ hiện hai
 * màu khác nhau ở hai trang và người dùng mất niềm tin vào cả hai.
 */
export function riskColor(score: number): string {
  if (score >= 80) return C.risk;
  if (score >= 60) return C.warn;
  return C.ok;
}

/** Nhãn mức độ tương ứng với `riskColor`. */
export function riskLabel(score: number): "NGHIÊM TRỌNG" | "CAO" | "TRUNG BÌNH" {
  if (score >= 80) return "NGHIÊM TRỌNG";
  if (score >= 60) return "CAO";
  return "TRUNG BÌNH";
}

/** Màu cho biến động: tăng chưa chắc là tốt trong AML, nên tách riêng hai hàm. */
export function deltaColor(delta: number, higherIsWorse = true): string {
  if (delta === 0) return C.inkLow;
  const bad = higherIsWorse ? delta > 0 : delta < 0;
  return bad ? C.riskSoft : C.ok;
}
