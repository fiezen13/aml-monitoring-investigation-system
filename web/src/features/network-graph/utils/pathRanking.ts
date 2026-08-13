import type { GEdge, GraphModel, MoneyPath } from "../types/graph.types";

/**
 * Liệt kê và xếp hạng đường đi của tiền.
 *
 * Chạy trên đồ thị *thật* chứ không phải đồ thị đã gộp cụm: nếu tìm trên bản
 * gộp thì một đường 7 chặng qua 12 mule sẽ rút thành 3 bước và con số "số hop"
 * mất hết ý nghĩa điều tra.
 */

const MAX_PATHS = 40;
const MAX_HOPS = 9;

/**
 * Một cạnh đơn nối hai đỉnh không phải là "đường đi của tiền" theo nghĩa điều
 * tra — nó chỉ là một giao dịch. Lọc chúng ra, nếu không những cạnh giá trị lớn
 * mà tầm thường (người chơi nạp vào nền tảng) sẽ chiếm hết đầu bảng xếp hạng.
 * Có đường lùi: nếu mạng lưới không có đường nào dài hơn thì vẫn hiện 1 hop còn
 * hơn để bảng trống.
 */
const MIN_HOPS = 2;

interface Candidates {
  sources: string[];
  targets: string[];
}

/** Nguồn = không có tiền chảy vào; đích = chặng cuối, hoặc không có tiền chảy ra. */
export function pathCandidates(model: GraphModel): Candidates {
  const moneyEdges = model.edges.filter((e) => e.money);
  const hasIn = new Set(moneyEdges.map((e) => e.t));
  const hasOut = new Set(moneyEdges.map((e) => e.s));

  const sources = model.nodes
    .filter((n) => !n.negative && hasOut.has(n.id) && !hasIn.has(n.id))
    .map((n) => n.id);

  const targets = model.nodes
    .filter((n) => !n.negative && hasIn.has(n.id) && (!hasOut.has(n.id) || n.stage === "destination"))
    .map((n) => n.id);

  return {
    sources: sources.length ? sources : model.nodes.filter((n) => n.stage === "source").map((n) => n.id),
    targets: targets.length ? targets : model.nodes.filter((n) => n.stage === "destination").map((n) => n.id),
  };
}

function minutesBetween(edges: GEdge[]): number {
  const times = edges.map((e) => new Date(e.knownFrom).getTime()).filter((v) => Number.isFinite(v));
  if (times.length < 2) return 0;
  return Math.round((Math.max(...times) - Math.min(...times)) / 60000);
}

function summarise(model: GraphModel, nodeIds: string[], edges: GEdge[], index: number): MoneyPath {
  // Giá trị của một đường là chỗ hẹp nhất: tiền không thể qua nhiều hơn khúc
  // nhỏ nhất trên đường đó. Lấy tổng sẽ thổi phồng con số.
  const amounts = edges.map((e) => e.amt).filter((v): v is number => v != null && v > 0);
  const amountUsd = amounts.length ? Math.min(...amounts) : 0;

  const confs = edges.map((e) => (e.inferred ? (e.conf ?? 0.5) : 1));
  const confidence = confs.length ? confs.reduce((a, b) => a * b, 1) ** (1 / confs.length) : 1;

  const channels = new Set(edges.map((e) => e.kind)).size;
  const riskAvg = nodeIds.reduce((s, id) => s + (model.byId[id]?.risk ?? 0), 0) / Math.max(1, nodeIds.length);

  // Điểm xếp hạng: tiền lớn, rủi ro cao, tin cậy cao thì lên trước; đường vòng
  // vèo quá nhiều chặng bị phạt nhẹ.
  const score =
    Math.log10(1 + amountUsd) * 26 + riskAvg * 0.75 + confidence * 30 - Math.max(0, edges.length - 6) * 4;

  return {
    id: `P${index}-${nodeIds[0]}-${nodeIds[nodeIds.length - 1]}-${edges.length}`,
    nodeIds,
    edgeIds: edges.map((e) => e.id),
    hops: edges.length,
    amountUsd,
    durationMin: minutesBetween(edges),
    channels,
    confidence,
    score,
  };
}

export function findMoneyPaths(model: GraphModel, sourceId?: string | null, targetId?: string | null): MoneyPath[] {
  const { sources, targets } = pathCandidates(model);
  const from = sourceId ? [sourceId] : sources;
  const to = new Set(targetId ? [targetId] : targets);
  if (!from.length || !to.size) return [];

  const adj = new Map<string, GEdge[]>();
  model.edges.forEach((e) => {
    if (!e.money) return;
    const arr = adj.get(e.s);
    if (arr) arr.push(e);
    else adj.set(e.s, [e]);
  });

  const out: MoneyPath[] = [];
  let counter = 0;

  const walk = (cur: string, nodePath: string[], edgePath: GEdge[], visited: Set<string>) => {
    if (out.length >= MAX_PATHS || edgePath.length > MAX_HOPS) return;
    if (to.has(cur) && edgePath.length) {
      out.push(summarise(model, [...nodePath], [...edgePath], counter++));
      return;
    }
    const next = adj.get(cur);
    if (!next) return;
    // Ưu tiên nhánh nhiều tiền trước để MAX_PATHS cắt vào đuôi chứ không cắt
    // mất đường quan trọng.
    [...next]
      .sort((a, b) => (b.amt ?? 0) - (a.amt ?? 0))
      .forEach((e) => {
        if (visited.has(e.t)) return;
        visited.add(e.t);
        nodePath.push(e.t);
        edgePath.push(e);
        walk(e.t, nodePath, edgePath, visited);
        edgePath.pop();
        nodePath.pop();
        visited.delete(e.t);
      });
  };

  from.forEach((s) => walk(s, [s], [], new Set([s])));

  const meaningful = out.filter((p) => p.hops >= MIN_HOPS);
  const ranked = meaningful.length ? meaningful : out;
  return ranked.sort((a, b) => b.score - a.score).slice(0, 12);
}

/**
 * Gợi ý điều tra cho panel phải khi chưa chọn gì.
 *
 * Không phải "top 4 điểm rủi ro" — như vậy sẽ ra bốn cái mule giống hệt nhau.
 * Mỗi gợi ý phải nói được một chuyện khác nhau: điểm ra tiền, cổng đổi tiền,
 * cụm thiết bị dùng chung, và đích đến cuối.
 */
export interface Lead {
  id: string;
  title: string;
  reason: string;
  nodeId: string | null;
  /** Bật đường tiền tương ứng khi bấm, nếu có. */
  pathId: string | null;
  severity: "high" | "elevated" | "medium";
  /** Tình trạng bằng chứng, nói thẳng cái gì đã quan sát được và cái gì chưa. */
  evidence: string;
}

export function buildLeads(model: GraphModel, paths: MoneyPath[], gapStages: Set<string> = new Set()): Lead[] {
  const leads: Lead[] = [];
  const push = (l: Lead) => {
    if (leads.length < 5 && l.nodeId) leads.push(l);
  };

  const byOut = [...model.nodes]
    .filter((n) => !n.negative && n.outUsd > 0)
    .sort((a, b) => b.outUsd - a.outUsd);

  const gateway = model.nodes.find((n) => n.stage === "gateway" && !n.negative);
  const destination = [...model.nodes]
    .filter((n) => n.stage === "destination" && !n.negative)
    .sort((a, b) => b.inUsd - a.inUsd)[0];
  const conversion = [...model.nodes]
    .filter((n) => n.stage === "conversion" && !n.negative)
    .sort((a, b) => b.risk - a.risk)[0];

  if (gateway) {
    push({
      id: "lead-gateway",
      title: gateway.label,
      reason: "Cổng chuyển fiat sang crypto",
      nodeId: gateway.id,
      pathId: paths.find((p) => p.nodeIds.includes(gateway.id))?.id ?? null,
      severity: "high",
      evidence: gapStages.has(gateway.stage) ? "Thiếu liên kết quan sát" : "Đã quan sát",
    });
  }

  if (conversion) {
    push({
      id: "lead-conversion",
      title: conversion.label,
      reason: conversion.role,
      nodeId: conversion.id,
      pathId: paths.find((p) => p.nodeIds.includes(conversion.id))?.id ?? null,
      severity: conversion.risk >= 80 ? "high" : "elevated",
      evidence: "Đã quan sát",
    });
  }

  const deviceCluster = model.clusters.find((c) => c.id === "CL-DEVICE");
  if (deviceCluster) {
    const linked = new Set<string>();
    model.edges.forEach((e) => {
      if (e.layer !== "device") return;
      if (deviceCluster.memberIds.includes(e.s)) linked.add(e.t);
      if (deviceCluster.memberIds.includes(e.t)) linked.add(e.s);
    });
    push({
      id: "lead-device",
      title: "Cụm thiết bị dùng chung",
      reason: `${linked.size} tài khoản dùng chung ${deviceCluster.memberIds.length} thiết bị`,
      nodeId: deviceCluster.memberIds[0],
      pathId: null,
      severity: "medium",
      evidence: `Suy luận ${deviceCluster.memberIds.length}/${deviceCluster.memberIds.length}`,
    });
  }

  if (destination) {
    push({
      id: "lead-destination",
      title: destination.label,
      reason: "Đích đến nhiều chặng của dòng tiền",
      nodeId: destination.id,
      pathId: paths.find((p) => p.nodeIds[p.nodeIds.length - 1] === destination.id)?.id ?? null,
      severity: "high",
      evidence: gapStages.has(destination.stage) ? "Thiếu liên kết quan sát" : "Suy luận trên chuỗi",
    });
  }

  if (leads.length < 4 && byOut[0]) {
    push({
      id: "lead-out",
      title: byOut[0].label,
      reason: "Giá trị chuyển ra lớn nhất mạng lưới",
      nodeId: byOut[0].id,
      pathId: null,
      severity: "elevated",
      evidence: "Đã quan sát",
    });
  }

  return leads;
}

/** Phát hiện chu trình tiền quay lại chủ thể ban đầu. */
export function detectCycles(model: GraphModel): string[][] {
  const adj = new Map<string, GEdge[]>();
  model.edges.forEach((e) => {
    if (!e.money) return;
    const arr = adj.get(e.s);
    if (arr) arr.push(e);
    else adj.set(e.s, [e]);
  });

  const cycles: string[][] = [];
  const seenKeys = new Set<string>();

  const walk = (start: string, cur: string, path: string[], depth: number) => {
    if (cycles.length >= 8 || depth > 7) return;
    (adj.get(cur) ?? []).forEach((e) => {
      if (e.t === start && path.length >= 2) {
        const key = [...path].sort().join("|");
        if (!seenKeys.has(key)) {
          seenKeys.add(key);
          cycles.push([...path, start]);
        }
        return;
      }
      if (path.includes(e.t)) return;
      walk(start, e.t, [...path, e.t], depth + 1);
    });
  };

  model.nodes.forEach((n) => walk(n.id, n.id, [n.id], 0));
  return cycles;
}
