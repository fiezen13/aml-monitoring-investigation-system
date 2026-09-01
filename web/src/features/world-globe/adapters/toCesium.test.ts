import { describe, expect, it } from "vitest";

import type { MapData, MapFlow, MapHub } from "../../../components/fc/WorldMap";
import {
  buildScene,
  greatCircleMeters,
  isValidCoordinate,
  severityOf,
  type FilterState,
} from "./toCesium";

const ALL_ON: FilterState = {
  layers: { bank: true, p2p: true, vasp: true, chain: true, gamb: true, proj: true },
  severity: "all",
  typology: "all",
  topN: 0,
  suspiciousOnly: false,
};

function hub(over: Partial<MapHub> = {}): MapHub {
  return {
    id: "US",
    name: "United States",
    lat: 37.09,
    lon: -95.71,
    size: 2,
    vol: "$1M",
    entities: 10,
    alerts: 0,
    riskN: 20,
    ...over,
  };
}

function flow(over: Partial<MapFlow> = {}): MapFlow {
  return {
    id: "GB-US-USD",
    sn: "United Kingdom",
    tn: "United States",
    slat: 55.38,
    slon: -3.44,
    tlat: 37.09,
    tlon: -95.71,
    ch: "bank",
    risk: "ok",
    vol: "$1M",
    txn: 20,
    typ: null,
    riskN: 30,
    ...over,
  };
}

function data(over: Partial<MapData> = {}): MapData {
  return { hubs: [hub()], flows: [flow()], ...over };
}

describe("toạ độ", () => {
  it("chấp nhận toạ độ WGS84 hợp lệ", () => {
    expect(isValidCoordinate(0, 0)).toBe(true);
    expect(isValidCoordinate(-180, -90)).toBe(true);
    expect(isValidCoordinate(180, 90)).toBe(true);
  });

  it("từ chối toạ độ ngoài dải, NaN và sai kiểu", () => {
    expect(isValidCoordinate(181, 0)).toBe(false);
    expect(isValidCoordinate(0, 91)).toBe(false);
    expect(isValidCoordinate(Number.NaN, 0)).toBe(false);
    expect(isValidCoordinate(Number.POSITIVE_INFINITY, 0)).toBe(false);
    expect(isValidCoordinate("10", 0)).toBe(false);
    expect(isValidCoordinate(undefined, undefined)).toBe(false);
  });

  it("loại node và hành lang có toạ độ hỏng, và nói rõ vì sao", () => {
    const scene = buildScene(
      data({
        hubs: [hub({ id: "BAD", lon: 999 })],
        flows: [flow({ id: "BAD-FLOW", tlat: Number.NaN })],
      }),
      ALL_ON,
    );
    expect(scene.nodes).toHaveLength(0);
    expect(scene.routes).toHaveLength(0);
    expect(scene.rejected.map((r) => r.id).sort()).toEqual(["BAD", "BAD-FLOW"]);
    // Toạ độ hỏng lọt xuống Cesium sẽ thành vệt kẻ vắt ngang quả cầu, nhìn như
    // lỗi dựng hình chứ không ai đoán ra là dữ liệu bẩn.
    expect(scene.rejected[0].reason).toMatch(/không hợp lệ/);
  });
});

describe("phân mức rủi ro", () => {
  it("dùng đúng ngưỡng như bảng điều khiển", () => {
    expect(severityOf(79)).toBe("warn");
    expect(severityOf(80)).toBe("crit");
    expect(severityOf(60)).toBe("warn");
    expect(severityOf(59)).toBe("ok");
  });
});

describe("kiểu vẽ hành lang", () => {
  it("bình thường: nét đứt, mảnh, mờ, không hoạt hoạ", () => {
    const [route] = buildScene(data({ flows: [flow({ risk: "ok" })] }), ALL_ON).routes;
    expect(route.dashed).toBe(true);
    expect(route.animated).toBe(false);
    expect(route.alpha).toBeLessThan(0.5);
  });

  it("đáng ngờ: nét liền, dày hơn, đậm hơn", () => {
    const [normal] = buildScene(data({ flows: [flow({ risk: "ok" })] }), ALL_ON).routes;
    const [susp] = buildScene(data({ flows: [flow({ risk: "warn" })] }), ALL_ON).routes;
    expect(susp.dashed).toBe(false);
    expect(susp.width).toBeGreaterThan(normal.width);
    expect(susp.alpha).toBeGreaterThan(normal.alpha);
  });

  it("nghiêm trọng: màu đỏ, dày nhất, có hoạt hoạ", () => {
    const [crit] = buildScene(data({ flows: [flow({ risk: "crit" })] }), ALL_ON).routes;
    expect(crit.color.toUpperCase()).toBe("#F45B69");
    expect(crit.animated).toBe(true);
    expect(crit.width).toBeGreaterThan(3);
  });

  it("giữ màu kênh cho hành lang chưa tới mức nghiêm trọng", () => {
    const [vasp] = buildScene(data({ flows: [flow({ ch: "vasp", risk: "warn" })] }), ALL_ON).routes;
    expect(vasp.color.toUpperCase()).toBe("#A78BFA");
  });

  it("kênh lạ không làm hỏng cảnh, chỉ lùi về màu ngân hàng", () => {
    const [odd] = buildScene(data({ flows: [flow({ ch: "Cheque" })] }), ALL_ON).routes;
    expect(odd.color.toUpperCase()).toBe("#4B9EFF");
  });
});

describe("bộ lọc", () => {
  const many: MapFlow[] = Array.from({ length: 50 }, (_, i) =>
    flow({ id: `F${i}`, riskN: i, risk: i >= 40 ? "crit" : i >= 30 ? "warn" : "ok" }),
  );

  it("Top N giữ đúng N hành lang rủi ro cao nhất", () => {
    for (const n of [10, 25, 50]) {
      const scene = buildScene(data({ flows: many }), { ...ALL_ON, topN: n });
      expect(scene.routes).toHaveLength(n);
    }
    const top10 = buildScene(data({ flows: many }), { ...ALL_ON, topN: 10 });
    expect(Math.min(...top10.routes.map((r) => r.flow.riskN ?? 0))).toBe(40);
  });

  it("Chỉ đáng ngờ loại hết hành lang bình thường", () => {
    const scene = buildScene(data({ flows: many }), { ...ALL_ON, suspiciousOnly: true });
    expect(scene.routes.every((r) => r.severity !== "ok")).toBe(true);
    expect(scene.routes).toHaveLength(20);
  });

  it("tắt một lớp kênh thì ẩn đúng kênh đó", () => {
    const mixed = [flow({ id: "A", ch: "bank" }), flow({ id: "B", ch: "vasp" })];
    const scene = buildScene(data({ flows: mixed }), {
      ...ALL_ON,
      layers: { ...ALL_ON.layers, vasp: false },
    });
    expect(scene.routes.map((r) => r.id)).toEqual(["A"]);
  });

  it("lọc không đụng tới node — bản đồ giữ nguyên các trung tâm", () => {
    const scene = buildScene(data({ flows: many }), { ...ALL_ON, topN: 10 });
    expect(scene.nodes).toHaveLength(1);
  });
});

describe("hình học cung", () => {
  it("đo được khoảng cách vòng lớn", () => {
    // Luân Đôn → New York, khoảng 5.570 km.
    const meters = greatCircleMeters(-0.13, 51.5, -74.0, 40.7);
    expect(meters / 1000).toBeGreaterThan(5_400);
    expect(meters / 1000).toBeLessThan(5_700);
  });

  it("hành lang cắt kinh tuyến 180° không vòng nửa vòng Trái Đất", () => {
    // Tokyo → Los Angeles đi qua Thái Bình Dương, không vòng qua châu Âu.
    const across = greatCircleMeters(139.7, 35.7, -118.2, 34.1);
    expect(across / 1000).toBeLessThan(9_500);
  });

  it("đỉnh cung bị chặn trần để không trông như quỹ đạo vệ tinh", () => {
    const [long] = buildScene(
      data({ flows: [flow({ slon: 139.7, slat: 35.7, tlon: -118.2, tlat: 34.1 })] }),
      ALL_ON,
    ).routes;
    expect(long.apexMeters).toBeLessThanOrEqual(420_000);
    expect(long.apexMeters).toBeGreaterThan(0);
  });
});

describe("cảnh rỗng", () => {
  it("không có dữ liệu thì trả cảnh rỗng chứ không ném lỗi", () => {
    const scene = buildScene(null, ALL_ON);
    expect(scene).toEqual({ nodes: [], routes: [], rejected: [] });
  });
});
