import type { FocusState, LayerKey, MoneyPath, PresetKey, RenderGraph } from "../types/graph.types";
import type { EdgeLevel } from "./graphStyles";
import { presetDef } from "./graphStyles";

/**
 * Quyết định mỗi đỉnh mờ bao nhiêu và mỗi cạnh thuộc tầng nào.
 *
 * Gom vào một chỗ vì ba cơ chế — preset, focus mode và isolate — chồng lên
 * nhau. Nếu để mỗi cơ chế tự sửa alpha lúc vẽ thì thứ tự áp dụng sẽ phụ thuộc
 * vào thứ tự gọi hàm, và cùng một trạng thái có thể ra hai kết quả khác nhau.
 *
 * Thứ tự ưu tiên, mạnh nhất trước: đường tiền đang chọn → focus → isolate →
 * preset.
 */

export interface EmphasisInput {
  graph: RenderGraph;
  preset: PresetKey;
  focus: FocusState;
  /** Đường tiền đang xem, nếu có. */
  activePath: MoneyPath | null;
  showAlternatives: boolean;
  /** Ngưỡng điểm để coi là "đáng ngờ" khi bật isolate. */
  suspiciousMin: number;
  /** Chế độ trình bày: chỉ mạch tiền chính sáng, mọi thứ khác lùi hẳn. */
  story: boolean;
}

export interface Emphasis {
  nodeAlpha: Map<string, number>;
  edgeLevel: Map<string, EdgeLevel>;
  /** Đỉnh bị ẩn hẳn (chỉ khi isolate ở chế độ cắt cứng). */
  hidden: Set<string>;
  /** Tập đỉnh đang được nhấn — dùng cho panel và đếm. */
  focused: Set<string>;
}

const DIM_NODE = 0.12;
const CONTEXT_NODE = 0.82;

/** Lan từ một đỉnh ra k bước, đi cả hai chiều cạnh. */
export function neighborhood(graph: RenderGraph, startId: string, hops: number): Set<string> {
  const seen = new Set<string>([startId]);
  let frontier = [startId];
  for (let i = 0; i < hops; i++) {
    const next: string[] = [];
    const inFrontier = new Set(frontier);
    graph.edges.forEach((e) => {
      if (inFrontier.has(e.s) && !seen.has(e.t)) {
        seen.add(e.t);
        next.push(e.t);
      }
      if (inFrontier.has(e.t) && !seen.has(e.s)) {
        seen.add(e.s);
        next.push(e.s);
      }
    });
    if (!next.length) break;
    frontier = next;
  }
  return seen;
}

function layerLevel(layer: LayerKey, emphasis: LayerKey[]): EdgeLevel {
  return emphasis.includes(layer) ? 2 : 3;
}

export function resolveEmphasis(input: EmphasisInput): Emphasis {
  const { graph, preset, focus, activePath, showAlternatives, suspiciousMin, story } = input;
  const def = presetDef(preset);

  const nodeAlpha = new Map<string, number>();
  const edgeLevel = new Map<string, EdgeLevel>();
  const hidden = new Set<string>();
  const focused = new Set<string>();

  const pathNodes = new Set(activePath?.nodeIds ?? []);
  const pathEdges = new Set(activePath?.edgeIds ?? []);

  const focusSet = focus.nodeId ? neighborhood(graph, focus.nodeId, focus.hops) : null;

  // Isolate: giữ node rủi ro cao, node trên đường tiền, và một vòng ngữ cảnh.
  let suspicious: Set<string> | null = null;
  if (focus.isolated) {
    const core = new Set<string>();
    graph.nodes.forEach((n) => {
      if (n.negative) return;
      if (n.risk >= suspiciousMin) core.add(n.id);
    });
    pathNodes.forEach((id) => core.add(id));
    if (focus.nodeId) core.add(focus.nodeId);
    suspicious = new Set(core);
    // Một hop ngữ cảnh quanh lõi, nếu không đồ thị sẽ rời rạc thành các chấm.
    graph.edges.forEach((e) => {
      if (core.has(e.s)) (suspicious as Set<string>).add(e.t);
      if (core.has(e.t)) (suspicious as Set<string>).add(e.s);
    });
  }

  graph.nodes.forEach((n) => {
    let alpha = 1;

    if (n.negative) alpha = showAlternatives ? 1 : 0.3;

    // Chế độ trình bày: mạch tiền chính (băng chính) sáng hẳn, quyền sở hữu và
    // thiết bị lùi về ngữ cảnh, đối chứng gần như tắt. Không đỉnh nào bị xoá —
    // chỉ đổi độ mờ, nên tắt chế độ là về nguyên trạng.
    if (story) {
      if (n.band === "primary") alpha = n.negative ? 0.1 : 1;
      else if (n.band === "support") alpha = 0.13;
      else alpha = 0.1;
    }

    if (suspicious) {
      if (!suspicious.has(n.id)) alpha = Math.min(alpha, showAlternatives && n.negative ? 0.35 : 0.14);
    }

    if (focusSet) {
      if (n.id === focus.nodeId) alpha = 1;
      else if (focusSet.has(n.id)) alpha = Math.max(alpha * CONTEXT_NODE, CONTEXT_NODE);
      else alpha = DIM_NODE;
    }

    if (pathNodes.size) {
      if (pathNodes.has(n.id)) alpha = 1;
      // Phần còn lại mờ đi nhưng *không* biến mất: analyst vẫn phải thấy đường
      // này nằm trong mạng lưới nào, nếu không nó chỉ là một chuỗi bảy đỉnh
      // trôi trên nền đen.
      else if (!focusSet) alpha = Math.min(alpha, 0.5);
    }

    if (alpha >= 0.5) focused.add(n.id);
    nodeAlpha.set(n.id, alpha);
  });

  graph.edges.forEach((e) => {
    let level: EdgeLevel = layerLevel(e.layer, def.emphasis);

    // Flow ưu tiên quan hệ tiền. Evidence giữ đủ lớp để analyst đối chiếu
    // quan sát/suy luận ngay tại đúng vị trí, không đổi bản đồ trong đầu.
    if (preset === "flow" && !e.money) level = 4;

    const negEdge = graph.byId[e.s]?.negative || graph.byId[e.t]?.negative;
    if (negEdge && !showAlternatives) level = 4;

    if (story) {
      const bothPrimary = graph.byId[e.s]?.band === "primary" && graph.byId[e.t]?.band === "primary";
      level = bothPrimary && e.money ? 2 : 4;
    }

    if (suspicious && !(suspicious.has(e.s) && suspicious.has(e.t))) level = 4;

    if (focusSet) {
      const touchesSel = e.s === focus.nodeId || e.t === focus.nodeId;
      const inside = focusSet.has(e.s) && focusSet.has(e.t);
      if (touchesSel) level = e.money ? 1 : 2;
      else if (inside) level = Math.min(level, 3) as EdgeLevel;
      else level = 4;
    }

    if (pathEdges.has(e.id)) level = 1;
    else if (pathEdges.size && !focusSet) level = Math.max(level, 3) as EdgeLevel;

    if (focus.edgeId === e.id) level = 1;

    edgeLevel.set(e.id, level);
  });

  // Cắt cứng chỉ khi isolate mà không có focus — lúc đó analyst muốn màn hình
  // sạch, còn khi đang focus thì ngữ cảnh mờ vẫn có ích.
  if (suspicious && !focusSet) {
    graph.nodes.forEach((n) => {
      if (!suspicious?.has(n.id) && (nodeAlpha.get(n.id) ?? 1) <= 0.15 && !n.negative) hidden.add(n.id);
    });
  }

  return { nodeAlpha, edgeLevel, hidden, focused };
}
