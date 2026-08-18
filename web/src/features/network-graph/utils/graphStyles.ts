import { C } from "../../../design/palette";
import { ENTITY_COLOR } from "../../../design/visualization";
import type { LayerKey, PresetKey, Tier } from "../types/graph.types";

/**
 * Bảng hình dạng, màu và kích thước của đồ thị.
 *
 * Canvas cần chuỗi màu thật nên mọi thứ ở đây lấy từ design token chứ không từ
 * class Tailwind. Màu theo loại thực thể đến từ `design/visualization` để đồ
 * thị, bản đồ và chú giải cùng gọi một con người là một màu.
 */

export type ShapeKind =
  | "circle"
  | "rect"
  | "rrect"
  | "diamond"
  | "diamond2"
  | "hex"
  | "octagon"
  | "warning"
  | "container"
  | "pill";

export interface TypeStyle {
  color: string;
  shape: ShapeKind;
  name: string;
  /** Ký hiệu một ký tự vẽ trong lòng node. */
  glyph: string;
}

export const TYPE_STYLE: Record<string, TypeStyle> = {
  person: { color: ENTITY_COLOR.person, shape: "circle", name: "Cá nhân", glyph: "P" },
  organisation: { color: C.agent, shape: "rrect", name: "Tổ chức", glyph: "O" },
  org: { color: C.agent, shape: "rrect", name: "Tổ chức", glyph: "O" },
  account: { color: C.info, shape: "rect", name: "Tài khoản", glyph: "A" },
  device: { color: C.inkLow, shape: "hex", name: "Thiết bị", glyph: "D" },
  wallet: { color: C.ok, shape: "diamond", name: "Ví", glyph: "W" },
  vasp: { color: C.agent, shape: "octagon", name: "VASP", glyph: "V" },
  platform: { color: C.inkSoft, shape: "octagon", name: "Nền tảng", glyph: "X" },
  contract: { color: C.warn, shape: "diamond2", name: "Hợp đồng thông minh", glyph: "C" },
  token: { color: C.token, shape: "pill", name: "Tài sản số", glyph: "$" },
  project: { color: C.token, shape: "rrect", name: "Dự án", glyph: "T" },
  alert: { color: C.risk, shape: "warning", name: "Cảnh báo", glyph: "!" },
  case: { color: C.riskSoft, shape: "container", name: "Vụ việc", glyph: "K" },
};

export function typeStyle(type: string): TypeStyle {
  return TYPE_STYLE[type] ?? TYPE_STYLE.account;
}

/**
 * Bán kính cơ sở, nhân theo tier.
 *
 * Con số này phải đọc cùng với mức phóng mà `fit()` chọn: đồ thị 8 cột thường
 * được phóng khoảng 0.7, nên đường kính thật trên màn hình bằng khoảng 1.4 lần
 * bán kính ở đây. Đặt 22 để đỉnh tier 1 ra tầm 50–55px — ngưỡng đọc được mà
 * không cần zoom.
 */
const BASE_RADIUS = 27;

const TIER_SCALE: Record<Tier, number> = { 1: 1.6, 2: 1.18, 3: 0.8 };

export function nodeRadius(tier: Tier, isCluster: boolean, count: number): number {
  const base = BASE_RADIUS * TIER_SCALE[tier];
  if (!isCluster) return base;
  // Cụm to hơn thành viên nhưng tăng theo log — 12 thành viên không được to gấp 12.
  return base * (1.12 + Math.min(0.4, Math.log10(1 + count) * 0.3));
}

/** Bốn tầng cạnh của mục 9. Level 1 là đường tiền đang chọn. */
export type EdgeLevel = 1 | 2 | 3 | 4;

export interface EdgeLevelStyle {
  alpha: number;
  width: number;
}

/**
 * Tầng nền không được xuống dưới 0.08: mạng lưới phụ vẫn phải *thấy được* thì
 * analyst mới biết mình đang nhìn một phần của cái gì. Biến mất hẳn thì đồ thị
 * trông như chỉ có mỗi đường tiền chính.
 */
export const EDGE_LEVEL: Record<EdgeLevel, EdgeLevelStyle> = {
  1: { alpha: 1, width: 3.6 },
  2: { alpha: 0.6, width: 2.1 },
  3: { alpha: 0.26, width: 1.2 },
  4: { alpha: 0.1, width: 0.9 },
};

/**
 * Màu đường tiền chính đổi theo chặng: càng gần đích càng nóng.
 *
 * Dùng màu để mã hoá *vị trí trên đường đi* chứ không chỉ mã hoá "được chọn" —
 * nhờ vậy nhìn một cái là biết tiền đang ở khúc nào của quá trình rửa.
 */
export function pathStageColor(stage: string): string {
  if (stage === "destination" || stage === "case") return C.risk;
  if (stage === "crypto" || stage === "gateway") return C.warn;
  return C.info;
}

export function edgeColor(opts: {
  onPath: boolean;
  selected: boolean;
  inferred: boolean;
  money: boolean;
  negative: boolean;
}): string {
  if (opts.onPath) return C.risk;
  if (opts.selected) return C.primary;
  if (opts.negative) return C.inkDim;
  if (opts.inferred) return C.agent;
  if (opts.money) return C.info;
  return C.inkLow;
}

export const LAYER_LABEL: Record<LayerKey, string> = {
  money: "Dòng tiền",
  entity: "Quan hệ thực thể",
  device: "Thiết bị / IP",
  alert: "Cảnh báo",
  case: "Thuộc vụ việc",
  negative: "Đối chứng hợp pháp",
};

export const LAYER_ORDER: LayerKey[] = ["money", "entity", "device", "alert", "case", "negative"];

export interface PresetDef {
  key: PresetKey;
  label: string;
  hint: string;
  /** Lớp bật sẵn. Lớp không có ở đây bị đẩy xuống tầng nền. */
  layers: LayerKey[];
  /** Lớp được nhấn mạnh (level 1–2); còn lại xuống level 3–4. */
  emphasis: LayerKey[];
  /** Cụm thu gọn mặc định khi vào preset. */
  collapseClusters: boolean;
}

export const PRESETS: PresetDef[] = [
  {
    key: "overview",
    label: "Overview",
    hint: "Cấu trúc, cụm và các điểm rủi ro chính của vụ việc.",
    layers: ["money", "entity", "device", "alert", "case", "negative"],
    emphasis: ["money"],
    collapseClusters: true,
  },
  {
    key: "flow",
    label: "Flow",
    hint: "Tiền vào bên trái, điểm hợp lưu và đích đến ở bên phải.",
    layers: ["money", "entity", "device", "alert", "case", "negative"],
    emphasis: ["money"],
    collapseClusters: true,
  },
  {
    key: "evidence",
    label: "Evidence",
    hint: "Phân biệt quan sát, suy luận và khoảng trống bằng chứng.",
    layers: ["money", "entity", "device", "alert", "case", "negative"],
    emphasis: ["money", "entity", "device"],
    collapseClusters: true,
  },
];

export function presetDef(key: PresetKey): PresetDef {
  return PRESETS.find((p) => p.key === key) ?? PRESETS[0];
}

/**
 * Chặng được Crypto Trail giữ lại. Preset này khác các preset khác ở chỗ nó cắt
 * theo node chứ không chỉ theo lớp cạnh.
 */
export const CRYPTO_STAGES = new Set(["conversion", "gateway", "crypto", "destination", "case"]);
