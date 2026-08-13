// Màu dùng cho canvas, SVG và spec biểu đồ.
//
// Tailwind chỉ sinh ra class CSS; canvas thì cần chuỗi màu thật. Hai nơi phải
// khớp nhau, nên bảng này là bản sao có chủ đích của `tailwind.config.js` —
// sửa một bên thì sửa cả bên kia.

export const C = {
  app: "#080D12",
  side: "#0C131B",
  panel: "#101820",
  elev: "#15212B",
  sunken: "#0A1017",

  primary: "#20C7A7",
  primaryHi: "#2FDDBA",

  inkHi: "#E6EDF3",
  inkMid: "#B6C4D0",
  inkSoft: "#91A2B1",
  inkLow: "#8397A8",
  inkDim: "#708597",

  risk: "#F45B69",
  riskSoft: "#FF8792",
  warn: "#F0B44D",
  warnSoft: "#F5CE8A",
  ok: "#4CC38A",
  okSoft: "#86DCB4",
  info: "#4B9EFF",
  infoSoft: "#8CC0FF",
  agent: "#A78BFA",
  agentSoft: "#C9B8FC",
  token: "#F08A5C",

  grid: "#141D26",
  line: "#1D2A35",
  lineStrong: "#293B49",
} as const;

/**
 * Thứ tự màu mặc định cho các series không chỉ định màu riêng.
 *
 * Mở đầu bằng xanh dương chứ không phải teal: teal là màu của "đang chọn", và
 * một biểu đồ mà series đầu tiên luôn teal thì tín hiệu đó mất nghĩa.
 */
export const SERIES = [C.info, C.agent, C.ok, C.warn, C.risk, C.token];

/**
 * Màu theo kênh dòng tiền — dùng chung bởi world map, network graph và chú giải.
 *
 * Không kênh nào lấy màu `primary`: trên bản đồ, teal dành riêng cho thực thể
 * đang được chọn, và nếu P2P cũng teal thì không phân biệt được "kênh P2P" với
 * "hành lang tôi vừa bấm".
 */
export const CHANNEL: Record<string, string> = {
  bank: C.info,
  p2p: "#38BDF8",
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
