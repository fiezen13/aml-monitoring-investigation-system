import { describe, expect, it } from "vitest";

import type { GCluster, RenderEdge, RenderGraph, RenderNode } from "../types/graph.types";
import { buildElements, edgeLabel, riskClass } from "./elements";

function node(over: Partial<RenderNode> = {}): RenderNode {
  return {
    id: "N1",
    kind: "node",
    label: "Tài khoản gom 1",
    shortLabel: "Gom 1",
    sub: "VCB •1234",
    role: "Tài khoản gom",
    type: "account",
    risk: 40,
    negative: false,
    stage: "aggregation",
    tier: 2,
    band: "primary",
    count: 1,
    t: 0.5,
    x: 0,
    y: 0,
    ref: null,
    cluster: null,
    parentClusterId: null,
    ...over,
  };
}

function edge(over: Partial<RenderEdge> = {}): RenderEdge {
  return {
    id: "REL-1",
    s: "N1",
    t: "N2",
    kind: "transfer",
    label: "",
    amt: 1000,
    inferred: false,
    conf: null,
    layer: "money",
    money: true,
    time: 0.5,
    count: 1,
    ref: null,
    txCount: 0,
    amountsByCurrency: {},
    ...over,
  };
}

function graph(nodes: RenderNode[], edges: RenderEdge[], openClusters: GCluster[] = []): RenderGraph {
  const byId: Record<string, RenderNode> = {};
  nodes.forEach((n) => (byId[n.id] = n));
  return { nodes, edges, byId, openClusters };
}

const NO_OPTS = { openClusterIds: new Set<string>(), clusterLabels: new Map<string, string>(), gaps: [] };

describe("riskClass", () => {
  it("dùng đúng ba ngưỡng như riskColor", () => {
    expect(riskClass(0)).toBe("");
    expect(riskClass(59)).toBe("");
    expect(riskClass(60)).toBe("risk-warn");
    expect(riskClass(79)).toBe("risk-warn");
    expect(riskClass(80)).toBe("risk-crit");
    expect(riskClass(100)).toBe("risk-crit");
  });
});

describe("edgeLabel", () => {
  it("ưu tiên số giao dịch thật", () => {
    expect(edgeLabel(edge({ txCount: 42, amountsByCurrency: { USD: 271_000 } }))).toContain("42 giao dịch");
  });

  it("không cộng nhiều loại tiền thành một số", () => {
    const label = edgeLabel(edge({ txCount: 5, amountsByCurrency: { USD: 120_000, EUR: 45_000 } }));
    expect(label).toContain("2 loại tiền");
    expect(label).not.toContain("165");
  });

  it("không ghi '0 giao dịch' cho quan hệ vốn không sinh giao dịch", () => {
    // Số 0 dễ bị đọc thành "đã kiểm tra và không có", trong khi sự thật là
    // "loại quan hệ này không có sổ cái ngân hàng để đối chiếu".
    const label = edgeLabel(edge({ kind: "owns", money: false, amt: null, txCount: 0 }));
    expect(label).not.toContain("0 giao dịch");
  });

  it("nói số quan hệ khi cạnh là kết quả gộp của cụm thu gọn", () => {
    expect(edgeLabel(edge({ amt: null, count: 4, txCount: 0 }))).toContain("4 quan hệ");
  });
});

describe("buildElements", () => {
  it("gắn class rủi ro theo điểm, không theo loại thực thể", () => {
    const els = buildElements(graph([node({ risk: 92 }), node({ id: "N2", risk: 10 })], []), NO_OPTS);
    const crit = els.find((e) => e.data.id === "N1");
    const calm = els.find((e) => e.data.id === "N2");
    expect(crit?.classes).toContain("risk-crit");
    expect(calm?.classes ?? "").not.toContain("risk");
  });

  it("không đặt nhãn thường trực cho đỉnh nào — nhãn do lớp zoom quyết định", () => {
    // Đây là luật §17: mặc định đồ thị không có chữ nào ngoài thứ lớp semantic
    // zoom bật lên. Dữ liệu nhãn vẫn có, nhưng nó chỉ là dữ liệu.
    const els = buildElements(graph([node()], []), NO_OPTS);
    const n = els.find((e) => e.data.id === "N1");
    expect(n?.data.short).toBe("Gom 1");
    expect(n?.data.label).toBe("Tài khoản gom 1");
    expect(n?.classes ?? "").not.toContain("labelled");
  });

  it("cụm thu gọn mang số thành viên trong nhãn ngắn", () => {
    const els = buildElements(
      graph([node({ kind: "cluster", label: "Tài khoản gom", count: 4 })], []),
      NO_OPTS,
    );
    expect(els[0].data.short).toBe("Tài khoản gom +4");
    expect(els[0].classes).toContain("collapsed-cluster");
    expect(els[0].data.isCluster).toBe(true);
  });

  it("dựng compound parent cho cụm đang mở và gán cha cho thành viên", () => {
    const members = [
      node({ id: "M1", parentClusterId: "CL-MULE" }),
      node({ id: "M2", parentClusterId: "CL-MULE" }),
    ];
    const els = buildElements(graph(members, []), {
      openClusterIds: new Set(["CL-MULE"]),
      clusterLabels: new Map([["CL-MULE", "Tài khoản trung chuyển"]]),
      gaps: [],
    });
    const parent = els.find((e) => e.data.id === "CL:CL-MULE");
    expect(parent?.classes).toContain("cluster-parent");
    expect(parent?.data.clusterLabel).toBe("Tài khoản trung chuyển");
    expect(els.filter((e) => e.data.parent === "CL:CL-MULE")).toHaveLength(2);
  });

  it("không gán cha khi cụm đang đóng", () => {
    const els = buildElements(graph([node({ id: "M1", parentClusterId: "CL-MULE" })], []), NO_OPTS);
    expect(els.find((e) => e.data.id === "M1")?.data.parent).toBeUndefined();
    expect(els.some((e) => e.data.id === "CL:CL-MULE")).toBe(false);
  });

  it("bỏ cạnh treo — đầu kia đã bị bộ lọc cắt", () => {
    const els = buildElements(graph([node()], [edge({ s: "N1", t: "MISSING" })]), NO_OPTS);
    expect(els.filter((e) => e.group === "edges")).toHaveLength(0);
  });

  it("chỗ đứt bằng chứng là phần tử riêng, không trộn vào cạnh quan hệ", () => {
    const els = buildElements(graph([node(), node({ id: "N2" })], [edge()]), {
      ...NO_OPTS,
      gaps: [{ id: "GAP-1", fromId: "N1", toId: "N2" }],
    });
    const edges = els.filter((e) => e.group === "edges");
    expect(edges).toHaveLength(2);
    const gap = edges.find((e) => e.classes === "evidence-gap");
    expect(gap?.data.isGap).toBe(true);
    // Quan hệ thật không bao giờ mang cờ đó — nhập chung thì một khoảng trống
    // bằng chứng sẽ bị đếm như một quan hệ có thật.
    expect(edges.find((e) => e.data.id === "REL-1")?.data.isGap).toBeUndefined();
  });

  it("bỏ chỗ đứt khi một đầu không còn hiển thị", () => {
    const els = buildElements(graph([node()], []), {
      ...NO_OPTS,
      gaps: [{ id: "GAP-1", fromId: "N1", toId: "KHONG-CO" }],
    });
    expect(els.filter((e) => e.group === "edges")).toHaveLength(0);
  });
});
