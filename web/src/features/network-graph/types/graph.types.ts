/**
 * Kiểu dữ liệu của Investigation Graph.
 *
 * Tách khỏi `FcGraphNode`/`FcGraphEdge` của API: API trả về thực thể thô, còn
 * màn hình này cần thêm ba thứ mà backend không biết — node nằm ở chặng nào của
 * dòng tiền, thuộc cụm nào, và quan trọng tới mức nào về mặt thị giác.
 */

/** Chặng trong dòng tiền, trái → phải. Số thứ tự chính là cột của layout. */
export const STAGES = [
  "source", // người chơi
  "ingress", // nền tảng cá cược, trung gian thanh toán — nơi tiền vào hệ thống ngân hàng
  "collection", // mule account
  "aggregation", // tài khoản gom
  "conversion", // P2P / OTC
  "gateway", // VASP
  "crypto", // ví trung gian
  "destination", // ví operator
  "case", // alert / vụ việc
] as const;

export type Stage = (typeof STAGES)[number];

export const STAGE_INDEX: Record<Stage, number> = Object.fromEntries(
  STAGES.map((s, i) => [s, i]),
) as Record<Stage, number>;

export const STAGE_LABEL: Record<Stage, string> = {
  source: "Nguồn",
  ingress: "Kênh nạp",
  collection: "Thu gom",
  aggregation: "Tài khoản gom",
  conversion: "Chuyển đổi",
  gateway: "Cổng VASP",
  crypto: "Ví tài sản mã hoá",
  destination: "Đích đến",
  case: "Cảnh báo",
};

/**
 * Ba mức ưu tiên thị giác. Đây là thứ quyết định kích thước node — không phải
 * bậc của đỉnh, vì bậc cao chưa chắc quan trọng (một mule có 10 cạnh vẫn chỉ là
 * mule).
 */
export type Tier = 1 | 2 | 3;

/** Băng ngang: dòng tiền chính ở giữa, phụ trợ ở dưới, đối chứng ở dưới cùng. */
export type Band = "primary" | "support" | "control";

export type LayerKey = "money" | "entity" | "device" | "alert" | "case" | "negative";

export type PresetKey = "overview" | "money" | "entity" | "device" | "crypto";

export type LayoutKey = "flow" | "force" | "hierarchy" | "community";

/** Mức chi tiết của nhãn, do zoom quyết định. */
export type ZoomLevel = "far" | "medium" | "close";

export interface GNode {
  id: string;
  type: string;
  label: string;
  /** Nhãn ngắn dùng ở zoom xa — bỏ hết mã kỹ thuật. */
  shortLabel: string;
  sub: string;
  /** Vai trò nghiệp vụ đã suy ra, ví dụ "Tài khoản gom". */
  role: string;
  risk: number;
  negative: boolean;
  stage: Stage;
  tier: Tier;
  band: Band;
  /** Cụm chứa node này; null nếu node đứng một mình. */
  clusterId: string | null;
  hub: string | null;
  first: string;
  last: string;
  /** Mốc xuất hiện chuẩn hoá 0→1 cho thanh thời gian. */
  t: number;
  /** Tổng tiền vào / ra, tính sẵn để inspector không phải quét lại cạnh. */
  inUsd: number;
  outUsd: number;
  degree: number;
}

export interface GEdge {
  id: string;
  s: string;
  t: string;
  kind: string;
  label: string;
  amt: number | null;
  inferred: boolean;
  conf: number | null;
  logic: string | null;
  knownFrom: string;
  /** Mốc thời gian chuẩn hoá 0→1. */
  time: number;
  layer: LayerKey;
  /** Cạnh nằm trên dòng tiền (transfer/swap/bridge…) — luôn ưu tiên vẽ. */
  money: boolean;

  /**
   * Chứng cứ giao dịch của quan hệ này, tổng hợp từ sổ cái thật.
   *
   * Đồ thị vẽ *quan hệ*, còn giao dịch là *sự kiện*. Bốn trường dưới đây là
   * cầu nối giữa hai tầng đó: chúng cho phép một cạnh nói được "tôi dựa trên
   * 42 lần chuyển khoản, từ ngày này tới ngày kia" mà không phải kéo cả 42
   * dòng lên màn hình.
   *
   * `txCount === 0` nghĩa là không có bằng chứng giao dịch — hợp lệ với quan
   * hệ sở hữu, thiết bị dùng chung hay chuyển on-chain.
   */
  txCount: number;
  amountsByCurrency: Record<string, number>;
  txFirstSeen: string | null;
  txLastSeen: string | null;
}

export interface GCluster {
  id: string;
  label: string;
  stage: Stage;
  band: Band;
  memberIds: string[];
  /** Rủi ro tóm tắt = điểm cao nhất trong cụm. */
  risk: number;
  /** Cụm chỉ chứa hard negative — dùng để làm mờ theo lớp "đối chứng". */
  negative: boolean;
}

export interface GraphModel {
  nodes: GNode[];
  edges: GEdge[];
  clusters: GCluster[];
  byId: Record<string, GNode>;
  /** Tổng tiền của mọi cạnh transfer, cho thẻ tóm tắt. */
  totalFlowUsd: number;
}

/**
 * Node sau khi gộp cụm: hoặc là node thật, hoặc là một cụm đang thu gọn.
 * Layout và engine chỉ làm việc với kiểu này.
 */
export interface RenderNode {
  id: string;
  kind: "node" | "cluster";
  label: string;
  shortLabel: string;
  sub: string;
  role: string;
  type: string;
  risk: number;
  negative: boolean;
  stage: Stage;
  tier: Tier;
  band: Band;
  count: number;
  t: number;
  /** Toạ độ do layout ghi vào. */
  x: number;
  y: number;
  /** Node thật bên trong, dùng cho hit-test và inspector. */
  ref: GNode | null;
  cluster: GCluster | null;
  /** Cụm cha đang mở — để vẽ hull bao quanh các thành viên. */
  parentClusterId: string | null;
}

export interface RenderEdge {
  id: string;
  s: string;
  t: string;
  kind: string;
  label: string;
  amt: number | null;
  inferred: boolean;
  conf: number | null;
  layer: LayerKey;
  money: boolean;
  time: number;
  /** Số cạnh thật đã gộp vào cạnh này (khi hai đầu là cụm thu gọn). */
  count: number;
  /** Cạnh thật gốc; null nếu là cạnh gộp. */
  ref: GEdge | null;
  /** Tổng số giao dịch của mọi cạnh thật đã gộp vào đây. */
  txCount: number;
  amountsByCurrency: Record<string, number>;
}

export interface RenderGraph {
  nodes: RenderNode[];
  edges: RenderEdge[];
  byId: Record<string, RenderNode>;
  /** Hull cần vẽ cho các cụm đang mở. */
  openClusters: GCluster[];
}

export interface MoneyPath {
  id: string;
  nodeIds: string[];
  edgeIds: string[];
  hops: number;
  amountUsd: number;
  /** Phút từ cạnh đầu tới cạnh cuối. */
  durationMin: number;
  /** Số loại kênh khác nhau đi qua (bank, p2p, vasp, chain…). */
  channels: number;
  confidence: number;
  score: number;
}

/**
 * Chỗ đứt của mạch điều tra.
 *
 * Đây *không* phải một quan hệ. Nó là ghi chú điều tra: hai chặng liền nhau
 * trong mạch tiền mà dữ liệu hiện có không hề quan sát được liên kết nào giữa
 * chúng. Phải tách hẳn khỏi `GEdge` — nhập chung thì một khoảng trống bằng
 * chứng sẽ bị đếm như một quan hệ có thật, và đó đúng là kiểu sai mà hệ thống
 * này tồn tại để tránh.
 */
export interface EvidenceGap {
  id: string;
  fromStage: Stage;
  toStage: Stage;
  fromNodeId: string;
  toNodeId: string;
  /** Những gì dữ liệu *có* nói về hai đầu. */
  known: string;
  /** Những gì còn thiếu để nối được. */
  missing: string;
  /** Nguồn dữ liệu hoặc công cụ có thể lấp khoảng trống này. */
  suggestion: string;
}

export interface FocusState {
  nodeId: string | null;
  edgeId: string | null;
  /** Bán kính lan toả quanh node đang chọn. */
  hops: number;
  /** Chỉ giữ node liên quan, ẩn hẳn phần còn lại. */
  isolated: boolean;
}
