/** Layout theo chiều dòng tiền.
 *
 * Bố cục cũ (fCoSE) xếp mọi đối tác quanh một tâm, nên không đọc được đâu là nơi
 * tiền đến, đâu là nơi tiền đi — câu hỏi đầu tiên của một chuyên viên AML.
 */

import { describe, expect, it } from "vitest";

import { dominantFlowNode, dominantFlowPositions, flowDepths } from "./layout";

const n = (id: string, inMoney: number, outMoney: number) => ({ id, inMoney, outMoney });

describe("flowDepths", () => {
  it("xếp nguồn tiền ở cột 0 và đích ở cột cuối", () => {
    const depth = flowDepths(
      [n("A", 0, 1), n("B", 1, 1), n("C", 1, 0)],
      [
        { s: "A", t: "B" },
        { s: "B", t: "C" },
      ],
    );
    expect(depth.A).toBe(0);
    expect(depth.B).toBe(1);
    expect(depth.C).toBe(2);
  });

  it("đẩy đỉnh hợp lưu về cột xa nhất, không bám nhánh ngắn", () => {
    // A→D trực tiếp, nhưng cũng A→B→C→D. D phải nằm sau C.
    const depth = flowDepths(
      [n("A", 0, 2), n("B", 1, 1), n("C", 1, 1), n("D", 2, 0)],
      [
        { s: "A", t: "B" },
        { s: "B", t: "C" },
        { s: "C", t: "D" },
        { s: "A", t: "D" },
      ],
    );
    expect(depth.D).toBe(3);
  });

  it("hình sao tách rõ bên gửi và bên nhận", () => {
    // Đúng hình dạng đang gây khó chịu: một tâm với nhiều đối tác hai phía.
    const depth = flowDepths(
      [n("in1", 0, 1), n("in2", 0, 1), n("hub", 2, 2), n("out1", 1, 0), n("out2", 1, 0)],
      [
        { s: "in1", t: "hub" },
        { s: "in2", t: "hub" },
        { s: "hub", t: "out1" },
        { s: "hub", t: "out2" },
      ],
    );
    expect(depth.in1).toBe(0);
    expect(depth.in2).toBe(0);
    expect(depth.hub).toBe(1);
    expect(depth.out1).toBe(2);
    expect(depth.out2).toBe(2);
  });

  it("đồ thị toàn chu trình vẫn có mốc, không bỏ trống bố cục", () => {
    const depth = flowDepths(
      [n("A", 1, 1), n("B", 1, 1)],
      [
        { s: "A", t: "B" },
        { s: "B", t: "A" },
      ],
    );
    expect(Object.keys(depth).sort()).toEqual(["A", "B"]);
    expect(Math.min(...Object.values(depth))).toBe(0);
  });

  it("đỉnh không nằm trên dòng tiền nào vẫn được xếp chỗ", () => {
    const depth = flowDepths([n("A", 0, 1), n("B", 1, 0), n("lonely", 0, 0)], [{ s: "A", t: "B" }]);
    expect(depth.lonely).toBeTypeOf("number");
  });

  it("bỏ qua cạnh trỏ tới đỉnh không có trong danh sách", () => {
    const depth = flowDepths([n("A", 0, 1)], [{ s: "A", t: "khong-ton-tai" }]);
    expect(depth.A).toBe(0);
    expect(depth["khong-ton-tai"]).toBeUndefined();
  });
});

describe("pattern-aware FAN-IN", () => {
  const sources = Array.from({ length: 12 }, (_, i) => n(`source-${i + 1}`, 0, 1));
  const hub = n("collector", 12, 1);
  const destination = n("destination", 1, 0);
  const edges = [
    ...sources.map((source) => ({ s: source.id, t: hub.id })),
    { s: hub.id, t: destination.id },
  ];

  it("nhận diện đúng điểm hợp lưu từ hướng cạnh thật", () => {
    expect(dominantFlowNode([...sources, hub, destination])).toEqual({ id: "collector", kind: "fan-in" });
  });

  it("đóng nguồn thành nhiều nhóm và đặt collector về phía phải", () => {
    const positions = dominantFlowPositions([...sources, hub, destination], edges);
    expect(positions).not.toBeNull();
    const sourceXs = new Set(sources.map((source) => Math.round(positions?.[source.id].x ?? 0)));
    expect(sourceXs.size).toBeGreaterThanOrEqual(3);
    expect(positions?.collector.x).toBeGreaterThan(Math.max(...sources.map((source) => positions?.[source.id].x ?? 0)));
    expect(positions?.destination.x).toBeGreaterThan(positions?.collector.x ?? 0);
  });

  it("ổn định giữa hai lần dựng", () => {
    expect(dominantFlowPositions([...sources, hub, destination], edges)).toEqual(
      dominantFlowPositions([...sources, hub, destination], edges),
    );
  });
});
