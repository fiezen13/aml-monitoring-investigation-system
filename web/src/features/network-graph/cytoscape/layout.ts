import type { LayoutOptions } from "cytoscape";

import type { LayoutKey } from "../types/graph.types";

/**
 * Cấu hình layout.
 *
 * fCoSE là lựa chọn mặc định cho khám phá mạng lưới: nó xử lý được compound
 * node (cụm đang mở) và cho ra bố cục ổn định giữa các lần chạy, hai thứ mà bộ
 * layout tự viết trước đây không có.
 *
 * Layout KHÔNG chạy liên tục. Nó chạy đúng bốn thời điểm — dựng đồ thị, mở
 * cụm, mở rộng lân cận, người dùng bấm sắp xếp lại (§23). Chạy lại ở mỗi lần
 * hover hay chọn thì mỗi thao tác của analyst lại làm cả mạng lưới nhảy chỗ, và
 * họ mất luôn bản đồ ghi nhớ trong đầu về nơi từng thực thể đứng.
 */

/** Chất lượng thấp hơn khi đồ thị lớn — chờ 3 giây để xếp đẹp là quá lâu. */
function quality(nodeCount: number): "draft" | "default" | "proof" {
  if (nodeCount > 240) return "draft";
  if (nodeCount > 90) return "default";
  return "proof";
}

export function fcoseOptions(nodeCount: number, animate: boolean): LayoutOptions {
  return {
    name: "fcose",
    quality: quality(nodeCount),
    randomize: true,
    animate,
    animationDuration: 420,
    fit: true,
    padding: 48,
    // Khoảng cách đỉnh: đủ để nhãn dưới đỉnh không đè lên đỉnh bên cạnh. Đây
    // là nguyên nhân trực tiếp của "nhiều node gần nhau bị chồng chữ".
    nodeSeparation: 130,
    idealEdgeLength: () => 140,
    edgeElasticity: () => 0.45,
    nodeRepulsion: () => 9000,
    gravity: 0.22,
    gravityRange: 3.2,
    // Cụm đang mở là compound node; nới thêm để khung cụm không ôm sát đỉnh.
    gravityCompound: 1.1,
    gravityRangeCompound: 1.4,
    nestingFactor: 0.15,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 24,
    tilingPaddingHorizontal: 24,
    uniformNodeDimensions: false,
  } as unknown as LayoutOptions;
}

/**
 * Layout theo chiều dòng tiền — TIỀN VÀO bên trái, chủ thể ở giữa, TIỀN RA bên phải.
 *
 * Vì sao cần: fCoSE tối ưu khoảng cách chứ không tối ưu ý nghĩa. Với một tài
 * khoản có 20 đối tác, nó xếp thành hình sao — mọi đỉnh quây quanh tâm, và người
 * đọc không phân biệt được đâu là nơi tiền đến, đâu là nơi tiền đi. Đó chính là
 * câu hỏi đầu tiên của một chuyên viên AML.
 *
 * Cột được tính bằng chiều cạnh tiền, không phải bằng lực hút:
 *
 *   cột 0   chỉ GỬI đi, không nhận      → nguồn tiền
 *   cột 1+  vừa nhận vừa gửi            → trung chuyển, xếp theo độ sâu
 *   cột N   chỉ NHẬN, không gửi         → đích đến
 *
 * `preset` trước đây trả về mà không có toạ độ nào, nên cytoscape dồn tất cả về
 * một điểm — chế độ này coi như chưa hiện thực.
 */

interface FlowNode {
  id: string;
  inMoney: number;
  outMoney: number;
}

/** Độ sâu theo chiều tiền: nguồn = 0, mỗi chặng sau cộng 1. */
export function flowDepths(nodes: FlowNode[], edges: { s: string; t: string }[]): Record<string, number> {
  const ids = new Set(nodes.map((n) => n.id));
  const adjacency = new Map<string, string[]>();
  edges.forEach((e) => {
    if (!ids.has(e.s) || !ids.has(e.t)) return;
    const list = adjacency.get(e.s);
    if (list) list.push(e.t);
    else adjacency.set(e.s, [e.t]);
  });

  const depth: Record<string, number> = {};
  // Nguồn = không nhận đồng nào. Đồ thị không có nguồn nào (toàn chu trình) thì
  // lấy đỉnh nhận ít nhất làm mốc, chứ không bỏ trống bố cục.
  let roots = nodes.filter((n) => n.inMoney === 0).map((n) => n.id);
  if (!roots.length && nodes.length) {
    const least = Math.min(...nodes.map((n) => n.inMoney));
    roots = nodes.filter((n) => n.inMoney === least).map((n) => n.id);
  }
  roots.forEach((id) => (depth[id] = 0));

  // Giữ khoảng cách DÀI nhất để đỉnh hợp lưu rơi hẳn về bên phải, thay vì bám
  // theo nhánh ngắn nhất và nằm chen giữa các chặng trước nó.
  // Trần độ sâu: một đường đi đơn không thể dài hơn số đỉnh trừ một. Không có
  // trần này thì đồ thị CÓ CHU TRÌNH làm độ sâu tăng vô hạn — mỗi vòng lại nới
  // thêm một bậc — cho tới khi chạm chốt bảo vệ, và cột cuối cùng là số vô nghĩa.
  const maxRelax = Math.max(1, nodes.length - 1);
  const queue = [...roots];
  let guard = 0;
  while (queue.length && guard < 20000) {
    guard += 1;
    const current = queue.shift() as string;
    (adjacency.get(current) ?? []).forEach((next) => {
      const candidate = depth[current] + 1;
      if (candidate > maxRelax) return;
      if (depth[next] == null || candidate > depth[next]) {
        depth[next] = candidate;
        queue.push(next);
      }
    });
  }

  // Đỉnh không nằm trên dòng tiền nào (chỉ có quan hệ phi tiền tệ) vẫn phải có
  // chỗ đứng — xếp về cột cuối thay vì chồng lên gốc toạ độ.
  const maxDepth = Math.max(0, ...Object.values(depth));
  nodes.forEach((n) => {
    if (depth[n.id] == null) depth[n.id] = n.outMoney === 0 ? maxDepth : 0;
  });
  return depth;
}

const COLUMN_WIDTH = 320;
const ROW_HEIGHT = 96;

function stableJitter(id: string): number {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) | 0;
  return ((Math.abs(hash) % 25) - 12) * 0.8;
}

/**
 * Nhận diện topology hợp lưu/phân tán áp đảo bằng bậc tiền thật.
 * Không dùng nhãn hay dữ liệu giả: chỉ đọc hướng của các cạnh đang có.
 */
export function dominantFlowNode(nodes: FlowNode[]): { id: string; kind: "fan-in" | "fan-out" } | null {
  if (nodes.length < 5) return null;
  // Mẫu được đánh giá trên số cạnh TIỀN, không trên tổng node: một mạng có
  // thêm device/identity context không được làm FAN-IN thật biến mất.
  const totalMoney = nodes.reduce((sum, node) => sum + node.inMoney, 0);
  const threshold = Math.max(4, Math.ceil(totalMoney * 0.5));
  const incoming = [...nodes].sort((a, b) => b.inMoney - a.inMoney)[0];
  const outgoing = [...nodes].sort((a, b) => b.outMoney - a.outMoney)[0];
  if (incoming.inMoney >= threshold && incoming.inMoney >= outgoing.outMoney) return { id: incoming.id, kind: "fan-in" };
  if (outgoing.outMoney >= threshold) return { id: outgoing.id, kind: "fan-out" };
  return null;
}

/**
 * Bố cục topology-aware cho FAN-IN/FAN-OUT.
 *
 * Nguồn không còn nằm trên một đường thẳng hoàn hảo. Chúng được đóng thành
 * 2–3 nhóm nhỏ, so le nhẹ nhưng hoàn toàn deterministic; điểm hợp lưu nằm
 * khoảng 65% chiều rộng để còn chỗ nhìn các chặng đi ra sau nó.
 */
export function dominantFlowPositions(
  nodes: FlowNode[],
  edges: { s: string; t: string }[],
): Record<string, { x: number; y: number }> | null {
  const dominant = dominantFlowNode(nodes);
  if (!dominant) return null;

  const inbound = edges.filter((e) => e.t === dominant.id).map((e) => e.s);
  const outbound = edges.filter((e) => e.s === dominant.id).map((e) => e.t);
  const packed = dominant.kind === "fan-in" ? inbound : outbound;
  if (packed.length < 4) return null;

  const position: Record<string, { x: number; y: number }> = {};
  const groups = Math.min(3, Math.max(2, Math.ceil(packed.length / 5)));
  const sorted = [...new Set(packed)].sort();
  const byGroup = Array.from({ length: groups }, () => [] as string[]);
  sorted.forEach((id, index) => byGroup[index % groups].push(id));

  byGroup.forEach((ids, group) => {
    const yOffset = ((ids.length - 1) * 112) / 2;
    ids.forEach((id, row) => {
      const sourceX = 80 + group * 170 + (row % 2) * 24;
      const x = dominant.kind === "fan-in" ? sourceX : 1080 - sourceX;
      position[id] = { x, y: row * 112 - yOffset + stableJitter(id) };
    });
  });

  position[dominant.id] = { x: dominant.kind === "fan-in" ? 720 : 360, y: 0 };

  // Các đỉnh còn lại đi theo chiều tiền ở phía còn trống. Quan hệ hỗ trợ
  // không nối tiền được đặt thành một dải thấp, không chồng vào mạch chính.
  const packedSet = new Set(sorted);
  const remaining = nodes.filter((n) => n.id !== dominant.id && !packedSet.has(n.id)).sort((a, b) => a.id.localeCompare(b.id));
  remaining.forEach((n, index) => {
    const connectedAfter = dominant.kind === "fan-in" ? outbound.includes(n.id) : inbound.includes(n.id);
    const x = dominant.kind === "fan-in" ? (connectedAfter ? 1040 : 560) : connectedAfter ? 40 : 520;
    position[n.id] = { x, y: (index - (remaining.length - 1) / 2) * 104 + stableJitter(n.id) };
  });

  return position;
}

function presetOptions(position: Record<string, { x: number; y: number }>, animate: boolean): LayoutOptions {
  return {
    name: "preset",
    animate,
    animationDuration: 360,
    fit: true,
    padding: 56,
    positions: (node: { id: () => string }) => position[node.id()] ?? { x: 0, y: 0 },
  } as unknown as LayoutOptions;
}

export function flowOptions(
  nodes: FlowNode[],
  edges: { s: string; t: string }[],
  animate: boolean,
): LayoutOptions {
  const dominant = dominantFlowPositions(nodes, edges);
  if (dominant) return presetOptions(dominant, animate);

  const depth = flowDepths(nodes, edges);
  const columns = new Map<number, string[]>();
  nodes.forEach((n) => {
    const column = depth[n.id] ?? 0;
    const list = columns.get(column);
    if (list) list.push(n.id);
    else columns.set(column, [n.id]);
  });

  const position: Record<string, { x: number; y: number }> = {};
  columns.forEach((ids, column) => {
    // Sắp trong cột theo id để bố cục ổn định giữa các lần chạy: analyst giữ
    // được bản đồ ghi nhớ về nơi từng tài khoản đứng.
    ids.sort();
    const offset = ((ids.length - 1) * ROW_HEIGHT) / 2;
    ids.forEach((id, index) => {
      // So le nhẹ để tránh “đội hình duyệt binh” và các cung bezier trùng nhau.
      const stagger = ids.length >= 5 ? (index % 3) * 26 : 0;
      position[id] = { x: column * COLUMN_WIDTH + stagger, y: index * ROW_HEIGHT - offset + stableJitter(id) };
    });
  });
  return presetOptions(position, animate);
}

export function layoutFor(
  key: LayoutKey,
  nodeCount: number,
  animate: boolean,
  flow?: { nodes: FlowNode[]; edges: { s: string; t: string }[] },
): LayoutOptions {
  if ((key === "flow" || key === "hierarchy") && flow?.nodes.length) {
    return flowOptions(flow.nodes, flow.edges, animate);
  }
  // Overview dùng packing có chủ đích khi topology là FAN-IN/FAN-OUT rõ rệt;
  // các mạng phức tạp hơn vẫn giao cho fCoSE xử lý cộng đồng/compound node.
  if (key === "force" && flow?.nodes.length) {
    const positions = dominantFlowPositions(flow.nodes, flow.edges);
    if (positions) return presetOptions(positions, animate);
  }
  return fcoseOptions(nodeCount, animate);
}
