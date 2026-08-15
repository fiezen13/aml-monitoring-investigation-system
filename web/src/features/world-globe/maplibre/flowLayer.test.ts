import { describe, expect, it } from "vitest";

import { buildFlowSpecs } from "../adapters/flowSpec";
import type { RouteDescriptor } from "../adapters/toCesium";
import { buildVertexData } from "./flowLayer";

/**
 * Kiểm phần thuần tính toán của lớp vẽ: bố cục đỉnh và cách chuẩn hoá quãng
 * đường. Không đụng tới WebGL — CI không có GPU, và những lỗi hay gặp nhất ở
 * đây là lỗi số học chứ không phải lỗi dựng hình.
 */

const STRIDE = 16;
/** Vị trí của `progress` trong mỗi đỉnh. */
const PROGRESS_OFFSET = 5;

function route(over: Partial<RouteDescriptor> = {}): RouteDescriptor {
  return {
    id: "R1",
    from: { lon: 10, lat: 20 },
    to: { lon: 40, lat: 30 },
    severity: "warn",
    color: "#F0B44D",
    width: 2,
    dashed: false,
    animated: true,
    alpha: 0.8,
    apexMeters: 120_000,
    flow: {
      id: "R1",
      sn: "A",
      tn: "B",
      slat: 20,
      slon: 10,
      tlat: 30,
      tlon: 40,
      ch: "bank",
      risk: "warn",
      vol: "$1B",
      volUsd: 1e9,
      txn: 100,
      typ: null,
    },
    ...over,
  };
}

function progressValues(data: Float32Array): number[] {
  const out: number[] = [];
  for (let i = 0; i < data.length; i += STRIDE) out.push(data[i + PROGRESS_OFFSET]);
  return out;
}

describe("bố cục đỉnh", () => {
  it("mỗi đỉnh đúng 16 float", () => {
    const routes = [route()];
    const data = buildVertexData(routes, buildFlowSpecs(routes, { selectedFlowId: null }));
    expect(data.length % STRIDE).toBe(0);
    expect(data.length).toBeGreaterThan(0);
  });

  it("hành lang không có mô tả chuyển động thì bị bỏ qua, không sinh đỉnh rác", () => {
    const data = buildVertexData([route()], new Map());
    expect(data.length).toBe(0);
  });
});

describe("chuẩn hoá quãng đường", () => {
  it("chạy từ 0 ở nguồn tới 1 ở đích", () => {
    const routes = [route()];
    const progress = progressValues(
      buildVertexData(routes, buildFlowSpecs(routes, { selectedFlowId: null })),
    );
    expect(progress[0]).toBeCloseTo(0, 5);
    expect(progress[progress.length - 1]).toBeCloseTo(1, 5);
  });

  it("tăng đơn điệu — gói tiền không được lùi giữa đường", () => {
    const routes = [route()];
    const progress = progressValues(
      buildVertexData(routes, buildFlowSpecs(routes, { selectedFlowId: null })),
    );
    for (let i = 1; i < progress.length; i++) {
      expect(progress[i]).toBeGreaterThanOrEqual(progress[i - 1] - 1e-6);
    }
  });

  it("hành lang cắt kinh tuyến 180° vẫn liên tục 0→1 qua cả hai mảnh", () => {
    // Tokyo → Los Angeles: vòng lớn đi qua Thái Bình Dương và bị cắt làm đôi.
    const crossing = route({
      id: "JP-US",
      from: { lon: 139.7, lat: 35.7 },
      to: { lon: -118.2, lat: 34.1 },
    });
    const progress = progressValues(
      buildVertexData([crossing], buildFlowSpecs([crossing], { selectedFlowId: null })),
    );
    expect(progress[0]).toBeCloseTo(0, 5);
    expect(progress[progress.length - 1]).toBeCloseTo(1, 5);
    // Nếu mảnh thứ hai khởi động lại từ 0 thì gói tiền sẽ nhảy về giữa Thái
    // Bình Dương mỗi vòng — đây chính là chốt chặn cho lỗi đó.
    for (let i = 1; i < progress.length; i++) {
      expect(progress[i]).toBeGreaterThanOrEqual(progress[i - 1] - 1e-6);
    }
  });
});

describe("nhiều hành lang trong một buffer", () => {
  it("gộp vào đúng một mảng để cả màn hình chỉ tốn một draw call", () => {
    const routes = [route(), route({ id: "R2", flow: { ...route().flow, id: "R2" } })];
    const specs = buildFlowSpecs(routes, { selectedFlowId: null });
    const single = buildVertexData([routes[0]], specs);
    const both = buildVertexData(routes, specs);
    // Hai hành lang cộng thêm cặp đỉnh suy biến nối hai dải tam giác.
    expect(both.length).toBeGreaterThan(single.length * 2 - STRIDE * 4);
  });
});
