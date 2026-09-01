import { describe, expect, it } from "vitest";

import type { GCluster, GEdge, GNode, GraphModel } from "../types/graph.types";
import { buildRenderGraph, type FilterState } from "./graphClustering";

/**
 * Gộp cạnh khi cụm đang thu gọn.
 *
 * Đây là chỗ dễ sai nhất của tầng tổng hợp: nhiều quan hệ thật đổ về cùng một
 * cặp đỉnh hiển thị, và số giao dịch đứng sau chúng phải cộng lại — nhưng số
 * *quan hệ* và số *giao dịch* là hai đơn vị khác nhau, còn tiền thì không được
 * cộng ngang loại.
 */

function node(id: string, over: Partial<GNode> = {}): GNode {
  return {
    id,
    type: "account",
    label: id,
    shortLabel: id,
    sub: "",
    role: "Tài khoản",
    risk: 50,
    negative: false,
    stage: "collection",
    tier: 2,
    band: "primary",
    clusterId: null,
    hub: null,
    first: "2026-01-01T00:00:00Z",
    last: "2026-01-02T00:00:00Z",
    t: 0.1,
    inUsd: 0,
    outUsd: 0,
    degree: 0,
    ...over,
  };
}

function edge(id: string, s: string, t: string, over: Partial<GEdge> = {}): GEdge {
  return {
    id,
    s,
    t,
    kind: "transfer",
    label: "",
    amt: 100,
    inferred: false,
    conf: null,
    logic: null,
    knownFrom: "2026-01-01T00:00:00Z",
    time: 0.1,
    layer: "money",
    money: true,
    txCount: 0,
    amountsByCurrency: {},
    txFirstSeen: null,
    txLastSeen: null,
    ...over,
  };
}

const FILTER: FilterState = {
  preset: "overview",
  layers: { money: true, entity: true, device: true, alert: true, case: true, negative: true },
  mutedKinds: {},
  riskMin: 0,
  minAmt: 0,
  timeT: 1,
  collapsed: { "CL-MULE": true },
  showAlternatives: false,
};

function model(nodes: GNode[], edges: GEdge[], clusters: GCluster[]): GraphModel {
  const byId: Record<string, GNode> = {};
  nodes.forEach((n) => (byId[n.id] = n));
  return { nodes, edges, clusters, byId, totalFlowUsd: 0, flowByCurrency: {} };
}

/**
 * Cụm băng "primary" giữ tới 4 thành viên tiêu biểu và chỉ gom *phần dư*. Vì
 * vậy phải có 6 thành viên thì mới có 2 rơi vào đỉnh gom, và cạnh của hai đỉnh
 * đó mới đổ về cùng một cặp để gộp.
 */
const MEMBERS = ["M1", "M2", "M3", "M4", "M5", "M6"];

const CLUSTER: GCluster = {
  id: "CL-MULE",
  label: "Tài khoản trung chuyển",
  stage: "collection",
  band: "primary",
  memberIds: MEMBERS,
  risk: 80,
  negative: false,
};

describe("gộp cạnh khi cụm thu gọn", () => {
  // Điểm rủi ro giảm dần theo thứ tự, nên M5 và M6 là phần dư bị gom.
  const nodes = [
    ...MEMBERS.map((id, i) => node(id, { clusterId: "CL-MULE", risk: 90 - i })),
    node("AGG", { stage: "aggregation" }),
  ];
  const filler = MEMBERS.slice(0, 4).map((id, i) => edge(`F${i}`, id, "AGG"));

  it("cộng dồn số giao dịch của mọi quan hệ đã gộp", () => {
    const edges = [
      ...filler,
      edge("R1", "M5", "AGG", { txCount: 5, amountsByCurrency: { USD: 500 } }),
      edge("R2", "M6", "AGG", { txCount: 3, amountsByCurrency: { USD: 300 } }),
    ];
    const g = buildRenderGraph(model(nodes, edges, [CLUSTER]), FILTER);
    const merged = g.edges.find((e) => e.count === 2);

    expect(merged).toBeDefined();
    expect(merged!.txCount).toBe(8);
    expect(merged!.amountsByCurrency).toEqual({ USD: 800 });
  });

  it("giữ từng loại tiền riêng, không cộng ngang loại", () => {
    const edges = [
      ...filler,
      edge("R1", "M5", "AGG", { txCount: 2, amountsByCurrency: { USD: 120_000 } }),
      edge("R2", "M6", "AGG", { txCount: 1, amountsByCurrency: { EUR: 45_000 } }),
    ];
    const g = buildRenderGraph(model(nodes, edges, [CLUSTER]), FILTER);
    const merged = g.edges.find((e) => e.count === 2);

    expect(merged!.amountsByCurrency).toEqual({ USD: 120_000, EUR: 45_000 });
    expect(Object.values(merged!.amountsByCurrency)).not.toContain(165_000);
  });

  it("nhãn cạnh gộp đếm quan hệ, không đếm giao dịch", () => {
    // Hai đơn vị khác nhau: 2 quan hệ đứng sau 8 lần chuyển khoản. Bản cũ ghi
    // "2 giao dịch" cho hai quan hệ, tức là gọi sai tên con số.
    const edges = [
      ...filler,
      edge("R1", "M5", "AGG", { txCount: 5 }),
      edge("R2", "M6", "AGG", { txCount: 3 }),
    ];
    const g = buildRenderGraph(model(nodes, edges, [CLUSTER]), FILTER);
    const merged = g.edges.find((e) => e.count === 2);

    expect(merged!.label).toBe("2 quan hệ");
    expect(merged!.txCount).toBe(8);
  });

  it("không sửa vào dữ liệu gốc khi cộng dồn", () => {
    const source = edge("R1", "M5", "AGG", { txCount: 5, amountsByCurrency: { USD: 500 } });
    const edges = [...filler, source, edge("R2", "M6", "AGG", { txCount: 3, amountsByCurrency: { USD: 300 } })];
    buildRenderGraph(model(nodes, edges, [CLUSTER]), FILTER);

    // Cạnh gộp phải sao chép từ điển tiền tệ; cộng thẳng lên object của model
    // sẽ làm hỏng dữ liệu dùng chung với inspector và panel.
    expect(source.amountsByCurrency).toEqual({ USD: 500 });
    expect(source.txCount).toBe(5);
  });

  it("mở cụm thì mỗi quan hệ đứng riêng, giữ nguyên số giao dịch của mình", () => {
    const edges = [
      edge("R1", "M5", "AGG", { txCount: 5, amountsByCurrency: { USD: 500 } }),
      edge("R2", "M6", "AGG", { txCount: 3, amountsByCurrency: { USD: 300 } }),
    ];
    const g = buildRenderGraph(model(nodes, edges, [CLUSTER]), { ...FILTER, collapsed: {} });

    expect(g.edges).toHaveLength(2);
    expect(g.edges.map((e) => e.txCount).sort()).toEqual([3, 5]);
    // Cạnh chưa gộp giữ tham chiếu tới quan hệ thật — đó là thứ endpoint
    // drill-down nhận vào để hỏi sổ cái.
    expect(g.edges.every((e) => e.ref !== null)).toBe(true);
  });
});
