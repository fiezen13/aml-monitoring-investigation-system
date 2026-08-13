import type {
  GCluster,
  GEdge,
  GNode,
  GraphModel,
  LayerKey,
  PresetKey,
  RenderEdge,
  RenderGraph,
  RenderNode,
} from "../types/graph.types";
import { CRYPTO_STAGES, presetDef } from "./graphStyles";

/**
 * Gộp cụm và lọc, cho ra đồ thị mà engine thực sự vẽ.
 *
 * Đây là chỗ thực hiện "progressive disclosure": cụm đang thu gọn biến thành
 * một đỉnh duy nhất, và mọi cạnh nối tới thành viên của nó được gộp lại. Nhờ
 * vậy Case Overview chỉ còn khoảng một tá đỉnh thay vì gần bốn chục.
 */

export interface FilterState {
  preset: PresetKey;
  layers: Record<LayerKey, boolean>;
  /** Kind cạnh bị tắt riêng ở phần Advanced; rỗng nghĩa là không chặn gì. */
  mutedKinds: Record<string, boolean>;
  riskMin: number;
  minAmt: number;
  /** Vị trí thanh thời gian 0→1. */
  timeT: number;
  /** Bộ cụm đang thu gọn. */
  collapsed: Record<string, boolean>;
  /** Làm nổi hard negative thay vì để mờ. */
  showAlternatives: boolean;
}

function nodePassesFilter(n: GNode, f: FilterState): boolean {
  if (n.risk < f.riskMin) return false;
  if (n.t > f.timeT) return false;
  if (n.negative && !f.layers.negative) return false;
  if (f.preset === "crypto" && !CRYPTO_STAGES.has(n.stage)) return false;
  if (f.preset === "device") {
    // Device view vẫn cần tài khoản để thấy thiết bị nối ai với ai, nhưng
    // không cần toàn bộ phần crypto ở cuối đường.
    if (n.stage === "crypto" || n.stage === "destination") return false;
  }
  return true;
}

function edgePassesFilter(e: GEdge, f: FilterState): boolean {
  if (!f.layers[e.layer]) return false;
  if (f.mutedKinds[e.kind]) return false;
  if (e.time > f.timeT) return false;
  if (f.minAmt > 0 && e.money && (e.amt ?? 0) < f.minAmt) return false;
  return true;
}

/** Cụm bị buộc thu gọn bởi preset, trừ khi người dùng đã mở tay. */
export function defaultCollapsed(clusters: GCluster[], preset: PresetKey): Record<string, boolean> {
  const collapse = presetDef(preset).collapseClusters;
  const out: Record<string, boolean> = {};
  clusters.forEach((c) => {
    // Cụm đối chứng luôn thu gọn: nó là ngữ cảnh, không phải đối tượng điều tra.
    out[c.id] = collapse || c.negative;
  });
  return out;
}

/**
 * Số thành viên hiện ra khi cụm đang thu gọn.
 *
 * Đây là điểm khác biệt so với bản trước, và là điểm quan trọng nhất của vòng
 * này: thu gọn *không* có nghĩa là biến cụm thành một đỉnh. Một cụm thu gọn vẫn
 * cho thấy vài thành viên tiêu biểu bên trong đường bao, kèm một đỉnh "+N" gom
 * phần còn lại. Nếu thu hết thành một đỉnh thì màn hình thành lưu đồ bảy ô,
 * analyst mất hoàn toàn cảm giác đang nhìn một mạng lưới thật.
 */
const REPRESENTATIVES: Record<string, number> = { primary: 4, support: 2, control: 2 };

/** Hậu tố của đỉnh gom phần dư trong một cụm thu gọn. */
const REST = "::rest";

export function buildRenderGraph(model: GraphModel, f: FilterState): RenderGraph {
  const visible = new Set<string>();
  model.nodes.forEach((n) => {
    if (nodePassesFilter(n, f)) visible.add(n.id);
  });

  const clusterById: Record<string, GCluster> = {};
  model.clusters.forEach((c) => (clusterById[c.id] = c));

  // Cụm chỉ được coi là thu gọn khi còn đủ thành viên để phải gom — nếu bộ lọc
  // đã cắt gần hết thì gộp lại chỉ gây khó hiểu.
  const collapsedClusters = new Set<string>();
  const liveByCluster = new Map<string, GNode[]>();
  model.clusters.forEach((c) => {
    const live = c.memberIds.map((id) => model.byId[id]).filter((n) => n && visible.has(n.id));
    if (!live.length) return;
    liveByCluster.set(c.id, live);
    if (f.collapsed[c.id] && live.length >= 2) collapsedClusters.add(c.id);
  });

  /**
   * Thành viên tiêu biểu của mỗi cụm thu gọn — lấy theo điểm rủi ro giảm dần.
   * Phần dư chỉ gom lại khi còn từ 2 thành viên trở lên; dư đúng 1 thì hiện
   * thẳng nó ra, vì một đỉnh "+1" vừa tốn chỗ vừa vô nghĩa.
   */
  const repsByCluster = new Map<string, Set<string>>();
  const restByCluster = new Map<string, GNode[]>();
  collapsedClusters.forEach((cid) => {
    const c = clusterById[cid];
    const live = [...(liveByCluster.get(cid) ?? [])].sort((a, b) => b.risk - a.risk);
    const k = REPRESENTATIVES[c.band] ?? 3;
    let reps = live.slice(0, k);
    let rest = live.slice(k);
    if (rest.length === 1) {
      reps = live;
      rest = [];
    }
    repsByCluster.set(cid, new Set(reps.map((n) => n.id)));
    restByCluster.set(cid, rest);
  });

  /** Node thật → id dùng khi vẽ (chính nó, hoặc đỉnh gom phần dư của cụm). */
  const renderIdOf = (nodeId: string): string => {
    const n = model.byId[nodeId];
    if (!n?.clusterId || !collapsedClusters.has(n.clusterId)) return nodeId;
    return repsByCluster.get(n.clusterId)?.has(nodeId) ? nodeId : `${n.clusterId}${REST}`;
  };

  const nodes: RenderNode[] = [];

  model.nodes.forEach((n) => {
    if (!visible.has(n.id)) return;
    // Thành viên bị gom vào phần dư thì không vẽ riêng.
    if (n.clusterId && collapsedClusters.has(n.clusterId) && !repsByCluster.get(n.clusterId)?.has(n.id)) return;
    nodes.push({
      id: n.id,
      kind: "node",
      label: n.label,
      shortLabel: n.shortLabel,
      sub: n.sub,
      role: n.role,
      type: n.type,
      risk: n.risk,
      negative: n.negative,
      stage: n.stage,
      tier: n.tier,
      band: n.band,
      count: 1,
      t: n.t,
      x: 0,
      y: 0,
      ref: n,
      cluster: null,
      parentClusterId: n.clusterId,
    });
  });

  collapsedClusters.forEach((cid) => {
    const c = clusterById[cid];
    const rest = restByCluster.get(cid) ?? [];
    if (rest.length < 2) return;
    const top = rest.reduce((a, b) => (b.risk > a.risk ? b : a));
    nodes.push({
      id: `${cid}${REST}`,
      kind: "cluster",
      label: `+${rest.length} ${c.label.toLowerCase()}`,
      shortLabel: `+${rest.length}`,
      sub: `${rest.length} thực thể còn lại · rủi ro cao nhất ${top.risk}`,
      role: c.label,
      type: top.type,
      risk: top.risk,
      negative: c.negative,
      stage: c.stage,
      tier: c.negative ? 3 : 2,
      band: c.band,
      count: rest.length,
      t: Math.min(...rest.map((m) => m.t)),
      x: 0,
      y: 0,
      ref: null,
      cluster: c,
      // Nằm trong cùng đường bao với các thành viên tiêu biểu.
      parentClusterId: cid,
    });
  });

  // Vẽ đường bao cho mọi cụm còn từ hai đỉnh trở lên trên màn hình, bất kể
  // đang thu hay đang mở. Bản trước chỉ vẽ cho cụm đang mở, nên Case Overview
  // — vốn thu hết — không có đường bao nào.
  const renderedPerCluster = new Map<string, number>();
  nodes.forEach((n) => {
    if (!n.parentClusterId) return;
    renderedPerCluster.set(n.parentClusterId, (renderedPerCluster.get(n.parentClusterId) ?? 0) + 1);
  });
  const openClusters: GCluster[] = model.clusters.filter((c) => (renderedPerCluster.get(c.id) ?? 0) >= 2);

  const byId: Record<string, RenderNode> = {};
  nodes.forEach((n) => (byId[n.id] = n));

  // Gộp cạnh: sau khi thu cụm, nhiều cạnh thật đổ về cùng một cặp đỉnh.
  const merged = new Map<string, RenderEdge>();
  model.edges.forEach((e) => {
    if (!edgePassesFilter(e, f)) return;
    if (!visible.has(e.s) || !visible.has(e.t)) return;
    const s = renderIdOf(e.s);
    const t = renderIdOf(e.t);
    if (s === t) return; // cạnh nội bộ cụm — ẩn khi cụm đang đóng
    if (!byId[s] || !byId[t]) return;

    const key = `${s}|${t}|${e.layer}|${e.kind}`;
    const existing = merged.get(key);
    if (existing) {
      existing.count += 1;
      if (e.amt != null) existing.amt = (existing.amt ?? 0) + e.amt;
      existing.inferred = existing.inferred && e.inferred;
      existing.time = Math.min(existing.time, e.time);
      existing.ref = null;
      // `count` là số *quan hệ* đã gộp, `txCount` là số *giao dịch* đứng sau
      // chúng — hai con số khác nhau và nhãn phải nói đúng con số nó đang nói.
      // Bản cũ ghi "n giao dịch" cho n quan hệ, tức là đếm nhầm đơn vị.
      existing.txCount += e.txCount;
      for (const [ccy, amount] of Object.entries(e.amountsByCurrency)) {
        existing.amountsByCurrency[ccy] = (existing.amountsByCurrency[ccy] ?? 0) + amount;
      }
      existing.label = `${existing.count} quan hệ`;
      return;
    }
    merged.set(key, {
      id: key,
      s,
      t,
      kind: e.kind,
      label: e.label,
      amt: e.amt,
      inferred: e.inferred,
      conf: e.conf,
      layer: e.layer,
      money: e.money,
      time: e.time,
      count: 1,
      ref: e,
      txCount: e.txCount,
      // Sao chép chứ không dùng chung tham chiếu: cạnh gộp sau đó cộng dồn vào
      // đây, và cộng thẳng lên object của model sẽ làm hỏng dữ liệu gốc.
      amountsByCurrency: { ...e.amountsByCurrency },
    });
  });

  return { nodes, edges: [...merged.values()], byId, openClusters };
}

/** Các cụm còn hiện, dùng cho panel và nút expand/collapse tất cả. */
export function activeClusters(model: GraphModel, f: FilterState): GCluster[] {
  return model.clusters.filter((c) =>
    c.memberIds.some((id) => {
      const n = model.byId[id];
      return n && nodePassesFilter(n, f);
    }),
  );
}
