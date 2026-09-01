import { describe, expect, it } from "vitest";

import { flowMotion } from "../../../design/flow";
import { buildFlowSpec, buildFlowSpecs, routePhase } from "./flowSpec";
import type { RouteDescriptor } from "./toCesium";

/**
 * Mô tả chuyển động là hợp đồng duy nhất giữa nghiệp vụ và hai bộ dựng hình.
 * Nếu nó lệch, bản đồ phẳng và quả cầu sẽ vẽ hai thứ khác nhau cho cùng một
 * hành lang — và đó là loại lỗi không ai phát hiện bằng cách nhìn từng màn một.
 */

function route(over: Partial<RouteDescriptor> = {}): RouteDescriptor {
  return {
    id: "GB-US",
    from: { lon: -3, lat: 55 },
    to: { lon: -95, lat: 37 },
    severity: "warn",
    color: "#F0B44D",
    width: 2.4,
    dashed: false,
    animated: true,
    alpha: 0.8,
    apexMeters: 200_000,
    flow: {
      id: "GB-US",
      sn: "United Kingdom",
      tn: "United States",
      slat: 55,
      slon: -3,
      tlat: 37,
      tlon: -95,
      ch: "bank",
      risk: "warn",
      vol: "$1B",
      volUsd: 1e9,
      txn: 500,
      typ: null,
    },
    ...over,
  };
}

describe("lệch pha", () => {
  it("tất định theo id — cùng id cho cùng pha ở mọi lần gọi", () => {
    expect(routePhase("GB-US")).toBe(routePhase("GB-US"));
    expect(routePhase("VN-SG")).toBe(routePhase("VN-SG"));
  });

  it("id khác nhau thì pha khác nhau, nếu không cả bản đồ nhấp nháy đồng loạt", () => {
    const phases = new Set(
      ["GB-US", "VN-SG", "DE-FR", "CN-US", "IT-ES", "BR-VASP"].map(routePhase),
    );
    expect(phases.size).toBe(6);
  });

  it("nằm trong khoảng 0–1", () => {
    for (const id of ["a", "b", "hành lang có dấu", "", "0"]) {
      const phase = routePhase(id);
      expect(phase).toBeGreaterThanOrEqual(0);
      expect(phase).toBeLessThan(1);
    }
  });
});

describe("ba biến, ba nghĩa", () => {
  it("bề rộng theo khối lượng, không theo mức rủi ro", () => {
    const small = buildFlowSpec(route({ flow: { ...route().flow, volUsd: 1e6 } }), {
      selectedFlowId: null,
    });
    const large = buildFlowSpec(route({ flow: { ...route().flow, volUsd: 1e11 } }), {
      selectedFlowId: null,
    });
    expect(large.width).toBeGreaterThan(small.width);
    expect(small.width).toBeCloseTo(flowMotion.minWidth, 5);
    expect(large.width).toBeCloseTo(flowMotion.maxWidth, 5);
  });

  it("tốc độ theo số giao dịch, và luôn nằm trong khoảng đã đặt", () => {
    const quiet = buildFlowSpec(route({ flow: { ...route().flow, txn: 1 } }), { selectedFlowId: null });
    const busy = buildFlowSpec(route({ flow: { ...route().flow, txn: 50_000 } }), {
      selectedFlowId: null,
    });
    expect(busy.speed).toBeGreaterThan(quiet.speed);
    expect(quiet.speed).toBeGreaterThanOrEqual(flowMotion.minSpeed);
    expect(busy.speed).toBeLessThanOrEqual(flowMotion.maxSpeed);
  });

  it("màu lấy nguyên từ hành lang, không tự chế trong lớp chuyển động", () => {
    expect(buildFlowSpec(route({ color: "#F45B69" }), { selectedFlowId: null }).color).toBe("#F45B69");
  });

  it("thiếu khối lượng thì lùi về bề rộng nhỏ nhất chứ không bịa ra giá trị", () => {
    const spec = buildFlowSpec(route({ flow: { ...route().flow, volUsd: undefined } }), {
      selectedFlowId: null,
    });
    expect(spec.width).toBeCloseTo(flowMotion.minWidth, 5);
  });
});

describe("mức độ rủi ro quyết định độ mờ của đường nền", () => {
  it("càng nghiêm trọng càng rõ", () => {
    const ok = buildFlowSpec(route({ severity: "ok" }), { selectedFlowId: null });
    const warn = buildFlowSpec(route({ severity: "warn" }), { selectedFlowId: null });
    const crit = buildFlowSpec(route({ severity: "crit" }), { selectedFlowId: null });
    expect(ok.baseOpacity).toBeLessThan(warn.baseOpacity);
    expect(warn.baseOpacity).toBeLessThan(crit.baseOpacity);
  });
});

describe("trạng thái chọn", () => {
  it("hành lang đang chọn dày hơn, sáng hơn và có vệt dài hơn", () => {
    const plain = buildFlowSpec(route(), { selectedFlowId: null });
    const picked = buildFlowSpec(route(), { selectedFlowId: "GB-US" });
    expect(picked.selected).toBe(true);
    expect(picked.width).toBeGreaterThan(plain.width);
    expect(picked.trailOpacity).toBeGreaterThan(plain.trailOpacity);
    expect(picked.trailLength).toBeGreaterThan(plain.trailLength);
  });

  it("hành lang không liên quan mờ đi nhưng KHÔNG tắt hẳn chuyển động", () => {
    const other = buildFlowSpec(route({ id: "DE-FR", flow: { ...route().flow, id: "DE-FR" } }), {
      selectedFlowId: "GB-US",
    });
    expect(other.dimmed).toBe(true);
    expect(other.baseOpacity).toBe(flowMotion.inactiveOpacity);
    // Vẫn còn vệt: tắt hẳn sẽ làm mất bối cảnh mạng lưới quanh hành lang đang xem.
    expect(other.trailOpacity).toBeGreaterThan(0);
  });
});

describe("giảm chuyển động", () => {
  it("vệt đứng yên và không còn phần sáng chuyển động", () => {
    const spec = buildFlowSpec(route(), { selectedFlowId: null, reducedMotion: true });
    expect(spec.speed).toBe(0);
    expect(spec.trailOpacity).toBe(0);
  });

  it("dồn phần sáng của vệt vào đường nền — không ai bị mất thông tin", () => {
    const normal = buildFlowSpec(route(), { selectedFlowId: null });
    const reduced = buildFlowSpec(route(), { selectedFlowId: null, reducedMotion: true });
    expect(reduced.baseOpacity).toBeGreaterThan(normal.baseOpacity);
    expect(reduced.baseOpacity).toBeLessThanOrEqual(0.9);
  });

  it("hành lang đang chọn vẫn phân biệt được", () => {
    const plain = buildFlowSpec(route(), { selectedFlowId: null, reducedMotion: true });
    const picked = buildFlowSpec(route(), { selectedFlowId: "GB-US", reducedMotion: true });
    expect(picked.width).toBeGreaterThan(plain.width);
    expect(picked.baseOpacity).toBeGreaterThan(plain.baseOpacity);
  });

  it("màu rủi ro không đổi", () => {
    expect(buildFlowSpec(route({ color: "#F45B69" }), { selectedFlowId: null, reducedMotion: true }).color).toBe(
      "#F45B69",
    );
  });
});

describe("buildFlowSpecs", () => {
  it("tra được theo id hành lang", () => {
    const specs = buildFlowSpecs([route(), route({ id: "DE-FR" })], { selectedFlowId: null });
    expect(specs.size).toBe(2);
    expect(specs.get("DE-FR")?.id).toBe("DE-FR");
  });
});
