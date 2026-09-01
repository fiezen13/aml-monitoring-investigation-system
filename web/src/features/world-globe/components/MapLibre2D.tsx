import { Map as MapLibreMap, setWorkerUrl, type MapGeoJSONFeature, type MapMouseEvent } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import "maplibre-gl/dist/maplibre-gl.css";

// MapLibre phân tích GeoJSON trong một Web Worker nằm ở file riêng. Mặc định nó
// tự suy ra đường dẫn worker từ `import.meta.url` của chính thư viện — đúng khi
// chạy từ node_modules, sai khi Vite đã gộp thư viện vào /assets/index-*.js: URL
// suy ra trỏ tới một file không tồn tại, worker chết, mọi nguồn GeoJSON kẹt ở
// trạng thái đang tải và bản đồ chỉ còn lớp nền đại dương — trống trơn, không
// một lỗi nào hiện ra.
//
// Phải là `?worker&url`, KHÔNG phải `?url`: bản dist của MapLibre 6 tách làm ba
// mảnh và maplibre-gl-worker.mjs mở đầu bằng `import "./maplibre-gl-shared.mjs"`.
// `?url` chỉ chép đúng một file nên worker gãy ngay ở dòng import đầu tiên; còn
// `?worker&url` bắt Vite build worker như một bundle riêng, gộp cả mảnh shared
// vào, rồi trả về đường dẫn asset đã băm. Dùng được cả ở dev lẫn production và
// không cần gọi ra Internet.
setWorkerUrl(workerUrl);

import type { MapData } from "../../../components/fc/WorldMap";
import { buildScene, type FilterState } from "../adapters/toCesium";
import {
  applySelection,
  FIRST_NODE_LAYER,
  installLayers,
  INTERACTIVE_LAYERS,
  NODE_LAYERS,
  updateData,
} from "../maplibre/layers";
import { darkBasemapStyle, WORLD_BOUNDS } from "../maplibre/style";
import { FlowLayer } from "../maplibre/flowLayer";
import { buildFlowSpecs } from "../adapters/flowSpec";
import { worldFlowClock } from "../state/flowClock";
import { useReduced } from "../../../design/motion";
import type { WorldCamera, WorldRendererHandle } from "../state/worldView";

interface Props {
  data: MapData | null;
  layers: Record<string, boolean>;
  sev: string;
  typ: string;
  topN: number;
  hideNormal: boolean;
  selectedFlow: string | null;
  selectedHub: string | null;
  onPickFlow: (id: string | null) => void;
  onPickHub: (id: string | null) => void;
  /** Khung nhìn ban đầu, lấy từ quả cầu ngay trước khi chuyển về bản dẹt. */
  initialCamera?: WorldCamera;
}

interface Hovered {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

/**
 * Bản đồ điều tra AML 2D.
 *
 * Không phải bản dẹt của quả cầu: 3D phục vụ nhận thức toàn cảnh, còn đây phục
 * vụ chuyên viên đọc hành lang — nền tối tối giản, tín hiệu AML nổi lên trên.
 */
export const MapLibre2D = forwardRef<WorldRendererHandle, Props>(function MapLibre2D(
  {
    data,
    layers,
    sev,
    typ,
    topN,
    hideNormal,
    selectedFlow,
    selectedHub,
    onPickFlow,
    onPickHub,
    initialCamera,
  },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const flowRef = useRef<FlowLayer | null>(null);
  const reduced = useReduced();
  const [ready, setReady] = useState(false);
  const [hovered, setHovered] = useState<Hovered | null>(null);
  const [fault, setFault] = useState<string | null>(null);

  // Giữ callback trong ref để việc WorldPage render lại không tháo lắp handler.
  const pickRef = useRef({ onPickFlow, onPickHub });
  pickRef.current = { onPickFlow, onPickHub };
  const initialCameraRef = useRef(initialCamera);
  initialCameraRef.current = initialCamera;

  /**
   * Bộ dựng hình đã lên hình được hay chưa.
   *
   * Không phải chuyện thừa: `new MapLibreMap()` trả về một đối tượng ngay cả
   * khi nó không lấy được context WebGL2 (GPU nằm trong danh sách chặn của
   * trình duyệt, phiên remote desktop, máy ảo không tăng tốc phần cứng). Đối
   * tượng đó tồn tại nhưng rỗng ruột, và `resize()` trên nó ném lỗi. Nếu handle
   * gọi thẳng thì cả màn Giám sát địa lý sập thay vì hiện thông báo lỗi và để
   * phần còn lại của bảng điều khiển chạy tiếp.
   */
  const healthyRef = useRef(false);

  /** Handle không được phép làm sập trang gọi nó. */
  const guard = (label: string, action: () => void) => {
    if (!healthyRef.current) return;
    try {
      action();
    } catch (err) {
      healthyRef.current = false;
      console.error(`[map2d] ${label} thất bại:`, err);
    }
  };

  useImperativeHandle(
    ref,
    (): WorldRendererHandle => ({
      getCamera() {
        const map = mapRef.current;
        if (!map || !healthyRef.current) return null;
        try {
          const center = map.getCenter();
          return { longitude: center.lng, latitude: center.lat, zoom: map.getZoom() };
        } catch {
          return null;
        }
      },
      setCamera(camera) {
        // `jumpTo` chứ không `flyTo`: khung nhìn này được đặt trong lúc lớp phủ
        // chuyển cảnh còn che, và một chuyến bay 2 giây bên dưới lớp mờ chỉ làm
        // bản đồ hiện ra khi đang giữa đường.
        guard("setCamera", () =>
          mapRef.current?.jumpTo({ center: [camera.longitude, camera.latitude], zoom: camera.zoom }),
        );
      },
      setActive(active) {
        guard("setActive", () => {
          const map = mapRef.current;
          if (!map) return;
          if (active) {
            map.resize();
            map.triggerRepaint();
          } else {
            // MapLibre không vẽ khi rảnh, nhưng có thể đang giữa một animation
            // camera; dừng lại để nó không chạy tiếp phía sau quả cầu.
            map.stop();
          }
        });
      },
    }),
    [],
  );

  const filter = useMemo<FilterState>(
    () => ({ layers, severity: sev, typology: typ, topN, suspiciousOnly: hideNormal }),
    [layers, sev, typ, topN, hideNormal],
  );
  const scene = useMemo(() => buildScene(data, filter), [data, filter]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const map = new MapLibreMap({
      container: host,
      style: darkBasemapStyle(),
      // center/zoom thay vì `bounds` trong constructor: fitBounds lúc khởi tạo
      // chạy trước khi container có kích thước cuối cùng, và map không bao giờ
      // phát `load`. Khung nhìn thế giới được đặt lại bằng fitBounds sau khi
      // style sẵn sàng, xem install() bên dưới.
      center: [10, 25],
      zoom: 1.1,
      attributionControl: false,
      // Bản đồ điều tra không cần nghiêng hay xoay; giữ Bắc luôn hướng lên để
      // so sánh hành lang giữa các phiên không bị lệch.
      pitchWithRotate: false,
      dragRotate: false,
      touchZoomRotate: true,
      renderWorldCopies: true,
    });
    mapRef.current = map;

    // MapLibre phát lỗi qua sự kiện `error`; không lắng nghe thì style hỏng sẽ
    // im lặng và bản đồ kẹt mãi ở trạng thái đang dựng.
    map.on("error", (event) => {
      const err = event?.error ?? event;
      console.error("[map2d] lỗi MapLibre:", err);
      healthyRef.current = false;
      setFault(err instanceof Error ? err.message : String(err));
    });

    // Bám vào `idle` chứ không chỉ `load`. Trong bản build production, `load`
    // có lúc không bắn với style thuần GeoJSON, và bản đồ kẹt mãi ở trạng thái
    // đang dựng; `idle` bắn mỗi khi map vẽ xong và rảnh, nên luôn tới.
    let installed = false;
    const install = () => {
      if (installed) return;
      // Đặt cờ TRƯỚC khi thêm nguồn. `map.getSource()` còn trả undefined khi
      // style chưa nạp xong, nên hai lần gọi sát nhau (styledata + rAF) đều lọt
      // qua chốt kiểm tra ở installLayers và lần thứ hai ném "already exists".
      installed = true;
      try {
        installLayers(map);
        // Vệt dòng tiền nằm trên hành lang nhưng dưới node: một trung tâm rủi
        // ro không bao giờ được bị vệt sáng đi ngang che mất.
        const flow = new FlowLayer();
        flowRef.current = flow;
        map.addLayer(flow, map.getLayer(FIRST_NODE_LAYER) ? FIRST_NODE_LAYER : undefined);
        healthyRef.current = true;
        const start = initialCameraRef.current;
        if (start) {
          map.jumpTo({ center: [start.longitude, start.latitude], zoom: start.zoom });
        } else {
          map.fitBounds(WORLD_BOUNDS, { padding: 12, animate: false });
        }
        setReady(true);
      } catch (err) {
        installed = false;
        healthyRef.current = false;
        console.error("[map2d] không cài được lớp AML:", err);
        setFault(err instanceof Error ? err.message : String(err));
      }
    };
    map.on("load", install);
    map.on("idle", install);
    // Container nằm trong layout flex và có thể chưa có kích thước ở thời điểm
    // khởi tạo; MapLibre khi đó không vẽ lần nào nên không phát load/idle. Ép
    // đo lại ở khung hình kế tiếp, và bám thêm `styledata` làm chốt cuối.
    map.on("styledata", install);
    requestAnimationFrame(() => {
      if (!mapRef.current) return;
      map.resize();
      install();
    });

    const pick = (event: MapMouseEvent) => {
      const hits = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYERS });
      const hit = hits[0] as MapGeoJSONFeature | undefined;
      const id = hit?.properties?.id as string | undefined;
      if (!id) {
        pickRef.current.onPickFlow(null);
        pickRef.current.onPickHub(null);
        return;
      }
      if (NODE_LAYERS.includes(hit!.layer.id as never)) {
        pickRef.current.onPickHub(id);
        pickRef.current.onPickFlow(null);
      } else {
        pickRef.current.onPickFlow(id);
        pickRef.current.onPickHub(null);
      }
    };

    const hover = (event: MapMouseEvent) => {
      const hits = map.queryRenderedFeatures(event.point, { layers: INTERACTIVE_LAYERS });
      const hit = hits[0] as MapGeoJSONFeature | undefined;
      map.getCanvas().style.cursor = hit ? "pointer" : "";
      if (!hit) {
        setHovered(null);
        return;
      }
      const props = hit.properties ?? {};
      const isNode = NODE_LAYERS.includes(hit.layer.id as never);
      setHovered({
        x: event.point.x,
        y: event.point.y,
        title: (props.name as string) ?? (props.id as string) ?? "",
        lines: [isNode ? "Trung tâm" : "Hành lang", severityLabel(props.severity as string)],
      });
    };

    map.on("click", pick);
    map.on("mousemove", hover);
    map.on("mouseout", () => setHovered(null));

    return () => {
      mapRef.current = null;
      flowRef.current = null;
      healthyRef.current = false;
      // `remove()` gỡ cả listener lẫn context WebGL; thiếu nó thì mỗi lần đổi
      // 2D↔3D rò rỉ một context và Chrome sẽ từ chối cấp cái tiếp theo. Bọc
      // try/catch vì chính `remove()` cũng ném khi map chưa dựng được painter.
      try {
        map.remove();
      } catch (err) {
        console.error("[map2d] không dọn được map:", err);
      }
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    updateData(map, scene);
    applySelection(map, selectedFlow, selectedHub);
  }, [ready, scene, selectedFlow, selectedHub]);

  /**
   * Dựng lại hình học của vệt dòng tiền.
   *
   * Chỉ chạy khi tập hành lang hoặc lựa chọn đổi — không phải mỗi khung hình.
   * Đồng hồ dòng chảy không bị đụng tới, nên đổi bộ lọc hay bấm Top 50 không
   * làm mọi gói tiền nhảy về vạch xuất phát.
   */
  useEffect(() => {
    if (!ready || !flowRef.current) return;
    const specs = buildFlowSpecs(scene.routes, {
      selectedFlowId: selectedFlow,
      reducedMotion: reduced,
    });
    flowRef.current.setRoutes(scene.routes, specs);
    mapRef.current?.triggerRepaint();
  }, [ready, scene, selectedFlow, reduced]);

  /**
   * Nhịp vẽ.
   *
   * MapLibre chỉ vẽ lại khi có gì đó đổi, nên phải chủ động yêu cầu khung hình
   * mới. Yêu cầu ấy đến từ đồng hồ dùng chung của World chứ không từ một
   * `requestAnimationFrame` riêng của bản đồ — cả màn hình chỉ có đúng một vòng
   * lặp, và quả cầu 3D đọc chung con số thời gian đó.
   *
   * Khi người dùng yêu cầu giảm chuyển động thì không đăng ký gì cả: đường nền
   * vẫn vẽ đủ, chỉ không có gói nào chạy.
   */
  useEffect(() => {
    if (!ready || reduced) return;
    return worldFlowClock.subscribe(() => {
      mapRef.current?.triggerRepaint();
    });
  }, [ready, reduced]);

  // Khung bản đồ nằm trong layout flex; ResizeObserver để canvas bám theo khi
  // dải phân tích phía dưới thu gọn hoặc cửa sổ đổi kích thước.
  useEffect(() => {
    const host = hostRef.current;
    const map = mapRef.current;
    if (!host || !map) return;
    const observer = new ResizeObserver(() => map.resize());
    observer.observe(host);
    return () => observer.disconnect();
  }, [ready]);

  return (
    <div className="absolute inset-0">
      {/* `h-full w-full` chứ không chỉ `absolute inset-0`: maplibre-gl.css đặt
          `.maplibregl-map { position: relative }` với cùng độ đặc hiệu như lớp
          `.absolute` của Tailwind, nên thứ tự file quyết định ai thắng. Từ khi
          các route nặng được tách thành chunk riêng, CSS của MapLibre nạp sau
          bundle chính và thắng — container mất `position:absolute`, `inset-0`
          hết tác dụng, chiều cao co về 0 và bản đồ biến mất mà không một lỗi
          nào được ném ra. Đặt kích thước tường minh thì đúng ở cả hai chiều
          thắng thua. */}
      <div ref={hostRef} className="absolute inset-0 h-full w-full" data-testid="maplibre-host" />

      {!ready && !fault && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-meta text-ink-low">
          Đang dựng bản đồ điều tra…
        </div>
      )}

      {fault && (
        <div className="absolute inset-x-3 top-3 z-hud rounded-control border border-risk/40 bg-risk/10 p-2 text-meta text-risk-soft">
          Bản đồ 2D lỗi: <span className="font-mono">{fault}</span>
        </div>
      )}

      {hovered && (
        <div
          className="pointer-events-none absolute z-hud max-w-[220px] rounded-control border border-line-strong bg-raised/95 px-2.5 py-1.5 text-meta shadow-popover backdrop-blur"
          style={{ left: hovered.x + 12, top: hovered.y + 12 }}
        >
          <div className="font-semibold text-ink-hi">{hovered.title}</div>
          {hovered.lines.map((line) => (
            <div key={line} className="text-ink-soft">
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

function severityLabel(severity: string): string {
  return severity === "crit" ? "Nghiêm trọng" : severity === "warn" ? "Đáng ngờ" : "Bình thường";
}
