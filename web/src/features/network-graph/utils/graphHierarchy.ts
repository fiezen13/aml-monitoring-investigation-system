import type { FcGraph, FcGraphEdge, FcGraphNode } from "../../../api/client";
import { formatDateTime } from "../../../api/format";
import type { Band, GCluster, GEdge, GNode, GraphModel, LayerKey, Stage, Tier } from "../types/graph.types";
import { STAGE_INDEX } from "../types/graph.types";

/**
 * Suy ra chặng, vai trò và mức ưu tiên thị giác cho từng thực thể.
 *
 * Backend không biết node nào là "mule" hay "tài khoản gom" — nó chỉ trả về
 * `entity_type`. Câu chuyện nghiệp vụ nằm ở tiền tố mã định danh do
 * `abm_generate.py` sinh ra, nên phần lớn việc ở đây là đọc tiền tố.
 *
 * Có chủ đích để một tầng dự phòng theo topology: nếu dữ liệu đổi và tiền tố
 * không còn khớp, đồ thị vẫn xếp được thành các cột theo khoảng cách từ nguồn,
 * thay vì dồn hết vào một cột.
 */

interface RoleRule {
  test: (id: string, node: FcGraphNode) => boolean;
  stage: Stage;
  band: Band;
  tier: Tier;
  role: string;
  /** Cụm mà node rơi vào; null nghĩa là node đứng riêng. */
  cluster: { id: string; label: string } | null;
  /** Nhãn ngắn dùng ở zoom xa. Bỏ trống thì dùng label gốc. */
  short?: (node: FcGraphNode) => string;
}

/** Cắt hậu tố số khỏi nhãn: "Mule 07" → "Mule". */
function stripIndex(label: string): string {
  return label.replace(/\s*[·\-–]?\s*\d+$/, "").trim();
}

const RULES: RoleRule[] = [
  {
    test: (id) => /^POOL/.test(id),
    stage: "source",
    band: "primary",
    tier: 2,
    role: "Nhóm người chơi",
    cluster: { id: "CL-PLAYERS", label: "Người chơi" },
    short: () => "Người chơi",
  },
  {
    // Nền tảng cá cược nhận tiền người chơi rồi điều phối trung gian thanh
    // toán — nó đứng ở kênh nạp chứ không phải nguồn.
    test: (id) => /^PLAT/.test(id),
    stage: "ingress",
    band: "primary",
    tier: 1,
    role: "Nền tảng cá cược",
    cluster: null,
  },
  {
    test: (id) => /^PER-OWN/.test(id),
    stage: "collection",
    band: "support",
    tier: 3,
    role: "Chủ tài khoản đứng tên",
    cluster: { id: "CL-OWNERS", label: "Chủ tài khoản" },
    short: () => "Chủ TK",
  },
  {
    test: (id) => /^ACC-MULE/.test(id),
    stage: "collection",
    band: "primary",
    tier: 2,
    role: "Tài khoản trung chuyển",
    cluster: { id: "CL-MULE", label: "Tài khoản mule" },
    short: (n) => stripIndex(n.label),
  },
  {
    test: (id) => /^DEV/.test(id),
    stage: "collection",
    band: "support",
    tier: 3,
    role: "Thiết bị dùng chung",
    cluster: { id: "CL-DEVICE", label: "Thiết bị dùng chung" },
    short: () => "Thiết bị",
  },
  {
    test: (id) => /^ACC-AGG/.test(id),
    stage: "aggregation",
    band: "primary",
    tier: 1,
    role: "Tài khoản gom",
    cluster: { id: "CL-AGG", label: "Tài khoản gom" },
    short: (n) => stripIndex(n.label),
  },
  {
    // Trung gian thanh toán *đẩy tiền vào* mule, không nhận từ mule. Xếp nó ở
    // chặng chuyển đổi như trực giác ban đầu sẽ tạo ra cạnh chạy ngược chiều và
    // phá vỡ toàn bộ tính đọc được của bố cục trái → phải.
    test: (id) => /^PSP/.test(id),
    stage: "ingress",
    band: "primary",
    tier: 1,
    role: "Trung gian thanh toán",
    cluster: null,
  },
  {
    test: (id) => /^PER-(P2P|OTC)/.test(id),
    stage: "conversion",
    band: "primary",
    tier: 2,
    role: "Đầu mối P2P / OTC",
    cluster: { id: "CL-P2P", label: "Đầu mối P2P / OTC" },
    short: (n) => stripIndex(n.label),
  },
  {
    test: (id) => /^VASP/.test(id),
    stage: "gateway",
    band: "primary",
    tier: 1,
    role: "Sàn giao dịch (VASP)",
    cluster: null,
  },
  {
    test: (id) => /^WAL-OP/.test(id),
    stage: "destination",
    band: "primary",
    tier: 1,
    role: "Ví operator",
    cluster: null,
    short: () => "Ví operator",
  },
  {
    test: (id) => /^WAL/.test(id),
    stage: "crypto",
    band: "primary",
    tier: 2,
    role: "Ví trung gian",
    cluster: { id: "CL-WALLET", label: "Cụm ví" },
    short: () => "Ví",
  },
  {
    test: (id, n) => /^ALR|^ALERT/.test(id) || n.type === "alert",
    stage: "case",
    band: "primary",
    tier: 1,
    role: "Cảnh báo",
    cluster: null,
  },
  {
    test: (id, n) => /^CASE/.test(id) || n.type === "case",
    stage: "case",
    band: "primary",
    tier: 1,
    role: "Vụ việc",
    cluster: null,
  },
];

/** Hard negative luôn xuống băng đối chứng, bất kể tiền tố. */
const NEGATIVE_CLUSTER = { id: "CL-ALT", label: "Đối chứng hợp pháp" };

interface Resolved {
  stage: Stage;
  band: Band;
  tier: Tier;
  role: string;
  clusterId: string | null;
  clusterLabel: string | null;
  shortLabel: string;
}

/** Chặng dự phòng khi không rule nào khớp — đoán theo `entity_type`. */
const TYPE_STAGE: Record<string, Stage> = {
  person: "source",
  account: "collection",
  organisation: "aggregation",
  platform: "ingress",
  vasp: "gateway",
  wallet: "crypto",
  contract: "crypto",
  token: "crypto",
  device: "collection",
  alert: "case",
  case: "case",
};

function resolve(node: FcGraphNode): Resolved {
  const rule = RULES.find((r) => r.test(node.id, node));

  if (node.negative) {
    // Đối chứng vẫn giữ chặng suy ra được để đứng đúng cột, nhưng bị đẩy xuống
    // băng riêng và hạ xuống tier 3 — chúng không được cạnh tranh thị giác với
    // mạng lưới nghi vấn.
    return {
      stage: rule?.stage ?? TYPE_STAGE[node.type] ?? "collection",
      band: "control",
      tier: 3,
      role: rule?.role ?? "Đối chứng hợp pháp",
      clusterId: NEGATIVE_CLUSTER.id,
      clusterLabel: NEGATIVE_CLUSTER.label,
      shortLabel: node.label,
    };
  }

  if (!rule) {
    return {
      stage: TYPE_STAGE[node.type] ?? "collection",
      band: "primary",
      tier: node.risk >= 85 ? 1 : node.risk >= 60 ? 2 : 3,
      role: node.type,
      clusterId: null,
      clusterLabel: null,
      shortLabel: node.label,
    };
  }

  return {
    stage: rule.stage,
    band: rule.band,
    tier: rule.tier,
    role: rule.role,
    clusterId: rule.cluster?.id ?? null,
    clusterLabel: rule.cluster?.label ?? null,
    shortLabel: rule.short ? rule.short(node) : node.label,
  };
}

/** Phân loại cạnh về một lớp để panel trái bật/tắt theo nhóm thay vì theo kind. */
const EDGE_LAYER: Record<string, LayerKey> = {
  transfer: "money",
  p2p: "money",
  deposit: "money",
  withdrawal: "money",
  crypto: "money",
  swap: "money",
  bridge: "money",
  owns: "entity",
  controls: "entity",
  control: "entity",
  director: "entity",
  device: "device",
  alert: "alert",
  member: "case",
  asset: "entity",
};

const MONEY_KINDS = new Set(["transfer", "p2p", "deposit", "withdrawal", "crypto", "swap", "bridge"]);

export function edgeLayerOf(kind: string): LayerKey {
  return EDGE_LAYER[kind] ?? "entity";
}

/**
 * Sắp lại chặng bằng topology khi tiền tố không đủ phân biệt.
 *
 * Chỉ chạy khi số chặng phân biệt được quá ít (dữ liệu lạ). Dùng khoảng cách
 * dài nhất từ các đỉnh không có cạnh tiền đi vào — đó chính là "nguồn".
 */
function topologicalStages(nodes: GNode[], edges: GEdge[]): void {
  const money = edges.filter((e) => e.money);
  if (!money.length) return;

  const indeg: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  nodes.forEach((n) => {
    indeg[n.id] = 0;
    adj[n.id] = [];
  });
  money.forEach((e) => {
    if (!(e.s in indeg) || !(e.t in indeg)) return;
    adj[e.s].push(e.t);
    indeg[e.t] += 1;
  });

  const depth: Record<string, number> = {};
  const queue = nodes.filter((n) => indeg[n.id] === 0).map((n) => n.id);
  queue.forEach((id) => (depth[id] = 0));

  // BFS nới lỏng: giữ khoảng cách dài nhất để node hợp lưu rơi về bên phải.
  let guard = 0;
  while (queue.length && guard < 20000) {
    guard += 1;
    const cur = queue.shift() as string;
    adj[cur].forEach((next) => {
      const cand = depth[cur] + 1;
      if (depth[next] == null || cand > depth[next]) {
        depth[next] = cand;
        queue.push(next);
      }
    });
  }

  const maxDepth = Math.max(1, ...Object.values(depth));
  const lastIndex = STAGE_INDEX.case;
  nodes.forEach((n) => {
    const d = depth[n.id];
    if (d == null) return;
    const scaled = Math.round((d / maxDepth) * (lastIndex - 1));
    n.stage = (Object.keys(STAGE_INDEX) as Stage[]).find((s) => STAGE_INDEX[s] === scaled) ?? n.stage;
  });
}

/** Số chặng phân biệt được — dưới 3 nghĩa là tiền tố không ăn, phải dự phòng. */
function distinctStages(nodes: GNode[]): number {
  return new Set(nodes.map((n) => n.stage)).size;
}

export function buildModel(raw: FcGraph): GraphModel {
  const times = raw.nodes.map((n) => new Date(n.first).getTime()).filter((v) => Number.isFinite(v));
  const edgeTimes = raw.edges.map((e) => new Date(e.known_from).getTime()).filter((v) => Number.isFinite(v));
  const all = [...times, ...edgeTimes];
  const min = all.length ? Math.min(...all) : 0;
  const span = Math.max(1, (all.length ? Math.max(...all) : 1) - min);

  const nodes: GNode[] = raw.nodes.map((n) => {
    const r = resolve(n);
    return {
      id: n.id,
      type: n.type,
      label: n.label,
      shortLabel: r.shortLabel,
      sub: n.sub ?? "",
      role: r.role,
      risk: n.risk,
      negative: n.negative,
      stage: r.stage,
      tier: r.tier,
      band: r.band,
      clusterId: r.clusterId,
      hub: n.hub,
      first: formatDateTime(n.first),
      last: formatDateTime(n.last),
      t: (new Date(n.first).getTime() - min) / span,
      inUsd: 0,
      outUsd: 0,
      degree: 0,
    };
  });

  const byId: Record<string, GNode> = {};
  nodes.forEach((n) => (byId[n.id] = n));

  const edges: GEdge[] = raw.edges
    .filter((e: FcGraphEdge) => byId[e.s] && byId[e.t])
    .map((e, i) => ({
      id: `E${i}-${e.s}-${e.t}-${e.kind}`,
      s: e.s,
      t: e.t,
      kind: e.kind,
      label: e.label ?? "",
      amt: e.amt,
      inferred: e.inferred,
      conf: e.conf,
      logic: e.logic,
      knownFrom: e.known_from,
      time: (new Date(e.known_from).getTime() - min) / span,
      layer: edgeLayerOf(e.kind),
      money: MONEY_KINDS.has(e.kind),
    }));

  if (distinctStages(nodes) < 3) topologicalStages(nodes, edges);

  let totalFlowUsd = 0;
  edges.forEach((e) => {
    byId[e.s].degree += 1;
    byId[e.t].degree += 1;
    if (e.money && e.amt != null) {
      byId[e.s].outUsd += e.amt;
      byId[e.t].inUsd += e.amt;
      totalFlowUsd += e.amt;
    }
  });

  // Cụm dựng từ nhãn đã gán ở `resolve`, giữ nguyên thứ tự gặp đầu tiên.
  const clusterMap = new Map<string, GCluster>();
  nodes.forEach((n) => {
    if (!n.clusterId) return;
    const label =
      n.negative
        ? NEGATIVE_CLUSTER.label
        : (RULES.find((r) => r.cluster?.id === n.clusterId)?.cluster?.label ?? n.clusterId);
    const existing = clusterMap.get(n.clusterId);
    if (existing) {
      existing.memberIds.push(n.id);
      existing.risk = Math.max(existing.risk, n.risk);
      existing.negative = existing.negative && n.negative;
      return;
    }
    clusterMap.set(n.clusterId, {
      id: n.clusterId,
      label,
      stage: n.stage,
      band: n.band,
      memberIds: [n.id],
      risk: n.risk,
      negative: n.negative,
    });
  });

  // Cụm một thành viên không đáng gộp — trả node về đứng riêng cho đỡ rối.
  const clusters: GCluster[] = [];
  clusterMap.forEach((c) => {
    if (c.memberIds.length < 2) {
      c.memberIds.forEach((id) => (byId[id].clusterId = null));
      return;
    }
    clusters.push(c);
  });

  return { nodes, edges, clusters, byId, totalFlowUsd };
}
