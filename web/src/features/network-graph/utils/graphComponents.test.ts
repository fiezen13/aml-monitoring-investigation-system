import { describe, expect, it } from "vitest";

import type { FcGraph, FcGraphNode } from "../../../api/client";
import { splitGraphComponents } from "./graphComponents";

function node(id: string, risk: number, alert = false): FcGraphNode {
  return {
    id,
    type: "account",
    label: id,
    sub: alert ? "Tài khoản có cảnh báo model" : "Tài khoản đối tác giao dịch",
    risk,
    first: "2022-01-01T00:00:00Z",
    last: "2022-01-01T00:00:00Z",
    hub: "0",
    negative: false,
  };
}

describe("splitGraphComponents", () => {
  it("không đặt hai mạng không nối nhau vào cùng component", () => {
    const raw: FcGraph = {
      nodes: [node("A", 90, true), node("B", 30), node("C", 80, true), node("D", 20)],
      edges: [
        { id: "AB", s: "A", t: "B", kind: "transfer", label: "", amt: null, inferred: false, conf: 1, logic: null, known_from: "2022-01-01T00:00:00Z", tx_count: 1, amounts_by_currency: {}, tx_first_seen: null, tx_last_seen: null },
        { id: "CD", s: "C", t: "D", kind: "transfer", label: "", amt: null, inferred: false, conf: 1, logic: null, known_from: "2022-01-01T00:00:00Z", tx_count: 1, amounts_by_currency: {}, tx_first_seen: null, tx_last_seen: null },
      ],
    };

    const components = splitGraphComponents(raw);
    expect(components).toHaveLength(2);
    expect(components[0].graph.nodes.map((item) => item.id).sort()).toEqual(["A", "B"]);
    expect(components[1].graph.nodes.map((item) => item.id).sort()).toEqual(["C", "D"]);
  });

  it("giữ node cô lập thành một mạng riêng", () => {
    const components = splitGraphComponents({ nodes: [node("A", 50)], edges: [] });
    expect(components[0]).toMatchObject({ id: "A", nodeCount: 1, edgeCount: 0 });
  });
});
