import { cleanup, render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MapData } from "../../../components/fc/WorldMap";
import type { WorldRendererHandle } from "../state/worldView";

/**
 * Mock hai module bọc Cesium chứ không mock cả `cesium`.
 *
 * Phần cần kiểm ở đây là điều phối: Viewer dựng đúng một lần, camera đặt được
 * từ bên ngoài qua handle, lọc chỉ vẽ lại cảnh, và unmount thì huỷ sạch. Kéo cả
 * bundle Cesium vào jsdom chỉ để khẳng định mấy điều đó là vừa chậm vừa cần WebGL
 * mà CI không có.
 */
const destroy = vi.fn();
const isDestroyed = vi.fn(() => false);
const setView = vi.fn();
const requestRender = vi.fn();
const resize = vi.fn();
const fakeViewer = {
  destroy,
  isDestroyed,
  resize,
  useDefaultRenderLoop: true,
  scene: { canvas: {}, requestRender },
  camera: { setView, positionCartographic: { longitude: 0.35, latitude: 0.65, height: 12_000_000 } },
};

const createScene = vi.fn(async () => ({ viewer: fakeViewer, imagery: "offline" as const }));
const syncScene = vi.fn();
const highlight = vi.fn();
const handlerDestroy = vi.fn();

vi.mock("../cesium/scene", () => ({
  createScene: (...args: unknown[]) => createScene(...(args as [])),
}));

vi.mock("../cesium/layers", () => ({
  syncScene: (...args: unknown[]) => syncScene(...(args as [])),
  highlight: (...args: unknown[]) => highlight(...(args as [])),
}));

vi.mock("cesium", () => ({
  Cartesian3: { fromDegrees: (lon: number, lat: number, height: number) => ({ lon, lat, height }) },
  Math: { toRadians: (deg: number) => (deg * Math.PI) / 180, toDegrees: (rad: number) => (rad * 180) / Math.PI },
  JulianDate: { now: () => ({}) },
  ScreenSpaceEventHandler: class {
    setInputAction = vi.fn();
    destroy = handlerDestroy;
  },
  ScreenSpaceEventType: { LEFT_CLICK: 0 },
}));

const { CesiumGlobe } = await import("./CesiumGlobe");

const DATA: MapData = {
  hubs: [
    { id: "US", name: "United States", lat: 37, lon: -95, size: 2, vol: "$1M", entities: 3, alerts: 0, riskN: 20 },
  ],
  flows: [
    {
      id: "GB-US",
      sn: "United Kingdom",
      tn: "United States",
      slat: 55,
      slon: -3,
      tlat: 37,
      tlon: -95,
      ch: "bank",
      risk: "ok",
      vol: "$1M",
      txn: 10,
      typ: null,
      riskN: 30,
    },
  ],
};

function props(over: Partial<Parameters<typeof CesiumGlobe>[0]> = {}) {
  return {
    data: DATA,
    layers: { bank: true, p2p: true, vasp: true, chain: true, gamb: true, proj: true },
    sev: "all",
    typ: "all",
    topN: 25,
    hideNormal: false,
    selectedFlow: null,
    selectedHub: null,
    onPickFlow: vi.fn(),
    onPickHub: vi.fn(),
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  isDestroyed.mockReturnValue(false);
  fakeViewer.useDefaultRenderLoop = true;
});

afterEach(cleanup);

describe("vòng đời Viewer", () => {
  it("dựng Viewer đúng một lần và vẽ cảnh sau khi sẵn sàng", async () => {
    render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    expect(createScene).toHaveBeenCalledTimes(1);
  });

  it("huỷ Viewer và handler khi unmount, không rò rỉ context WebGL", async () => {
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    view.unmount();
    expect(destroy).toHaveBeenCalledTimes(1);
    expect(handlerDestroy).toHaveBeenCalledTimes(1);
  });

  it("không huỷ Viewer đã bị huỷ lần nữa", async () => {
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    isDestroyed.mockReturnValue(true);
    view.unmount();
    expect(destroy).not.toHaveBeenCalled();
  });
});

describe("liên tục không gian khi chuyển 2D ↔ 3D", () => {
  it("đặt camera vào đúng vùng đất của bản đồ 2D ngay khi dựng", async () => {
    render(<CesiumGlobe {...props({ initialCamera: { longitude: 103.8, latitude: 1.35, zoom: 4 } })} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());

    // Camera phải được đặt TRƯỚC khi quả cầu hiện ra; đặt sau sẽ thành một cú
    // nhảy ngay trước mắt người dùng.
    const destination = setView.mock.calls[0]?.[0]?.destination;
    expect(destination.lon).toBeCloseTo(103.8, 5);
    expect(destination.lat).toBeCloseTo(1.35, 5);
    expect(destination.height).toBeGreaterThan(0);
  });

  it("handle đọc được khung nhìn hiện tại để trả về cho bản đồ 2D", async () => {
    const ref = createRef<WorldRendererHandle>();
    render(<CesiumGlobe ref={ref} {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());

    const camera = ref.current!.getCamera();
    expect(camera).not.toBeNull();
    expect(camera!.longitude).toBeCloseTo(20.05, 1);
    expect(camera!.zoom).toBeGreaterThan(0);
  });

  it("tắt vòng lặp dựng hình khi không phải bộ dựng đang hiển thị", async () => {
    const ref = createRef<WorldRendererHandle>();
    render(<CesiumGlobe ref={ref} {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());

    ref.current!.setActive(false);
    expect(fakeViewer.useDefaultRenderLoop).toBe(false);

    ref.current!.setActive(true);
    expect(fakeViewer.useDefaultRenderLoop).toBe(true);
    expect(resize).toHaveBeenCalled();
  });
});

describe("bộ lọc", () => {
  it("đổi Top N chỉ vẽ lại cảnh, không dựng lại Viewer", async () => {
    const view = render(<CesiumGlobe {...props({ topN: 10 })} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    createScene.mockClear();
    syncScene.mockClear();

    view.rerender(<CesiumGlobe {...props({ topN: 50 })} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    expect(createScene).not.toHaveBeenCalled();
  });

  it("bật Chỉ đáng ngờ cũng không dựng lại Viewer", async () => {
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalled());
    createScene.mockClear();

    view.rerender(<CesiumGlobe {...props({ hideNormal: true })} />);
    await waitFor(() => expect(syncScene).toHaveBeenCalledTimes(2));
    expect(createScene).not.toHaveBeenCalled();
  });
});

describe("trạng thái chọn", () => {
  it("đổi thực thể đang chọn thì làm nổi, không vẽ lại từ đầu", async () => {
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(highlight).toHaveBeenCalledWith(fakeViewer, null, null));

    view.rerender(<CesiumGlobe {...props({ selectedFlow: "GB-US" })} />);
    await waitFor(() => expect(highlight).toHaveBeenCalledWith(fakeViewer, "GB-US", null));
  });
});

describe("trạng thái tải và lỗi", () => {
  it("hiện trạng thái đang nạp thay vì canvas trắng", () => {
    const view = render(<CesiumGlobe {...props()} />);
    expect(view.getByText(/Đang nạp bản đồ Trái Đất/)).toBeInTheDocument();
  });

  it("Cesium hỏng thì báo lỗi chứ không làm sập bảng điều khiển", async () => {
    createScene.mockRejectedValueOnce(new Error("WebGL không khả dụng"));
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(view.getByText(/Không dựng được bản đồ Trái Đất/)).toBeInTheDocument());
    expect(view.getByText(/WebGL không khả dụng/)).toBeInTheDocument();
  });

  it("báo rõ khi đang chạy bằng ảnh nền ngoại tuyến", async () => {
    const view = render(<CesiumGlobe {...props()} />);
    await waitFor(() => expect(view.getByText(/Ảnh nền ngoại tuyến/)).toBeInTheDocument());
  });
});
