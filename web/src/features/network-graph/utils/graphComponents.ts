import type { FcGraph, FcGraphEdge, FcGraphNode } from "../../../api/client";

export interface GraphComponent {
  id: string;
  label: string;
  nodeCount: number;
  edgeCount: number;
  maxRisk: number;
  graph: FcGraph;
}

/**
 * Tách đồ thị thô thành các connected component theo quan hệ vô hướng.
 *
 * Đây chỉ là bước chọn phạm vi hiển thị: hướng của cạnh giao dịch vẫn được giữ
 * nguyên trong `graph`. Hai cụm không có cạnh nối tuyệt đối không được đặt lên
 * cùng canvas vì khoảng cách hình học khi đó không mang ý nghĩa nghiệp vụ.
 */
export function splitGraphComponents(raw: FcGraph): GraphComponent[] {
  const nodeById = new Map(raw.nodes.map((node) => [node.id, node]));
  const adjacency = new Map<string, Set<string>>();
  for (const node of raw.nodes) adjacency.set(node.id, new Set());
  for (const edge of raw.edges) {
    if (!nodeById.has(edge.s) || !nodeById.has(edge.t)) continue;
    adjacency.get(edge.s)!.add(edge.t);
    adjacency.get(edge.t)!.add(edge.s);
  }

  const seen = new Set<string>();
  const slices: Array<{ nodes: FcGraphNode[]; edges: FcGraphEdge[]; root: FcGraphNode }> = [];

  for (const start of raw.nodes) {
    if (seen.has(start.id)) continue;
    const ids = new Set<string>();
    const stack = [start.id];
    seen.add(start.id);
    while (stack.length) {
      const id = stack.pop()!;
      ids.add(id);
      for (const next of adjacency.get(id) ?? []) {
        if (seen.has(next)) continue;
        seen.add(next);
        stack.push(next);
      }
    }

    const nodes = raw.nodes.filter((node) => ids.has(node.id));
    const edges = raw.edges.filter((edge) => ids.has(edge.s) && ids.has(edge.t));
    const root = [...nodes].sort((a, b) => {
      const alertA = a.sub?.includes("cảnh báo") ? 1 : 0;
      const alertB = b.sub?.includes("cảnh báo") ? 1 : 0;
      return alertB - alertA || b.risk - a.risk || a.id.localeCompare(b.id);
    })[0];
    slices.push({ nodes, edges, root });
  }

  slices.sort(
    (a, b) =>
      Math.max(...b.nodes.map((node) => node.risk)) - Math.max(...a.nodes.map((node) => node.risk)) ||
      b.edges.length - a.edges.length ||
      b.nodes.length - a.nodes.length ||
      a.root.id.localeCompare(b.root.id),
  );

  return slices.map((slice, index) => ({
    id: slice.root.id,
    label: `Mạng ${String(index + 1).padStart(2, "0")} · ${slice.root.label}`,
    nodeCount: slice.nodes.length,
    edgeCount: slice.edges.length,
    maxRisk: Math.max(...slice.nodes.map((node) => node.risk)),
    graph: { nodes: slice.nodes, edges: slice.edges },
  }));
}
