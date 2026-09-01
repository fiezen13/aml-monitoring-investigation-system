import {
  Cartesian3,
  Math as CesiumMath,
  JulianDate,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Viewer,
} from "cesium";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import type { MapData } from "../../../components/fc/WorldMap";
import { buildScene, type FilterState } from "../adapters/toCesium";
import { buildFlowSpecs } from "../adapters/flowSpec";
import { useReduced } from "../../../design/motion";
import { highlight, syncScene } from "../cesium/layers";
import { createScene, type ImagerySource } from "../cesium/scene";
import { heightToZoom, zoomToHeight, type WorldCamera, type WorldRendererHandle } from "../state/worldView";

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
  /** Khung nhìn ban đầu, lấy từ bộ dựng hình 2D ngay trước khi chuyển. */
  initialCamera?: WorldCamera;
  onReady?: () => void;
}

/**
 * Quả cầu Trái Đất Cesium mang lớp phủ tình báo AML.
 *
 * Viewer được dựng đúng một lần và sống suốt vòng đời component. Đổi bộ lọc hay
 * đổi lựa chọn đều chỉ tác động lên cảnh — không dựng lại Viewer, vì làm vậy sẽ
 * mất camera, mất lựa chọn, và rò rỉ một context WebGL mỗi lần.
 *
 * Component luôn ở chế độ 3D. Bản dẹt của thế giới do MapLibre đảm nhiệm; giữ
 * thêm đường morph 2D của Cesium chỉ tạo ra hai bản đồ phẳng khác nhau với hai
 * bảng màu khác nhau — đúng thứ mà lần refactor này dẹp đi.
 */
export const CesiumGlobe = forwardRef<WorldRendererHandle, Props>(function CesiumGlobe(
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
    onReady,
  },
  ref,
) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [ready, setReady] = useState(false);
  const [imagery, setImagery] = useState<ImagerySource | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Giữ callback trong ref: nếu đưa thẳng vào deps của effect gắn sự kiện thì
  // mỗi lần cha render lại sẽ tháo và gắn lại handler của Cesium.
  const pickRef = useRef({ onPickFlow, onPickHub });
  pickRef.current = { onPickFlow, onPickHub };
  const initialCameraRef = useRef(initialCamera);
  initialCameraRef.current = initialCamera;
  const readyRef = useRef(onReady);
  readyRef.current = onReady;

  const filter = useMemo<FilterState>(
    () => ({ layers, severity: sev, typology: typ, topN, suspiciousOnly: hideNormal }),
    [layers, sev, typ, topN, hideNormal],
  );
  const scene = useMemo(() => buildScene(data, filter), [data, filter]);
  const reduced = useReduced();
  const flowSpecs = useMemo(
    () => buildFlowSpecs(scene.routes, { selectedFlowId: selectedFlow, reducedMotion: reduced }),
    [scene.routes, selectedFlow, reduced],
  );

  const viewportHeight = () => hostRef.current?.clientHeight || 720;

  /**
   * Handle không được phép làm sập trang gọi nó.
   *
   * Cesium dựng được Viewer rồi vẫn có thể hỏng giữa chừng — mất context WebGL,
   * GPU bị reset. Cùng lý do với `guard` bên MapLibre2D: màn Giám sát địa lý
   * phải suy giảm chứ không sập.
   */
  const guard = (label: string, action: () => void) => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    try {
      action();
    } catch (err) {
      console.error(`[globe] ${label} thất bại:`, err);
    }
  };

  useImperativeHandle(
    ref,
    (): WorldRendererHandle => ({
      getCamera() {
        const viewer = viewerRef.current;
        if (!viewer || viewer.isDestroyed()) return null;
        try {
          const carto = viewer.camera.positionCartographic;
          const latitude = CesiumMath.toDegrees(carto.latitude);
          return {
            longitude: CesiumMath.toDegrees(carto.longitude),
            latitude,
            zoom: heightToZoom(carto.height, latitude, viewportHeight()),
          };
        } catch {
          return null;
        }
      },
      setCamera(camera) {
        guard("setCamera", () => {
          const viewer = viewerRef.current!;
          viewer.camera.setView({
            destination: Cartesian3.fromDegrees(
              camera.longitude,
              camera.latitude,
              zoomToHeight(camera.zoom, camera.latitude, viewportHeight()),
            ),
            // Nhìn thẳng xuống, đúng như bản đồ 2D. Đây là điểm mấu chốt của
            // tính liên tục: người dùng thấy chính khung hình mình vừa xem, chỉ
            // khác là bây giờ nó nằm trên một mặt cầu. Nghiêng camera lúc này
            // sẽ biến việc đổi phép chiếu thành một chuyến bay tới nơi khác.
            orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
          });
        });
      },
      setActive(active) {
        guard("setActive", () => {
          const viewer = viewerRef.current!;
          viewer.useDefaultRenderLoop = active;
          if (active) {
            viewer.resize();
            // Một khung hình ép ngay lập tức: nếu không, quả cầu hiện ra vẫn
            // còn mang nội dung của lần dừng trước trong khoảng một khung.
            viewer.scene.requestRender();
          }
        });
      },
    }),
    [],
  );

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    let handler: ScreenSpaceEventHandler | null = null;

    createScene(host, import.meta.env.VITE_CESIUM_ION_TOKEN)
      .then((handle) => {
        if (disposed) {
          handle.viewer.destroy();
          return;
        }
        viewerRef.current = handle.viewer;
        setImagery(handle.imagery);

        // Đặt camera vào đúng vùng đất mà bản đồ 2D đang hiển thị, TRƯỚC khi
        // quả cầu hiện ra. Đặt sau sẽ thành một cú nhảy camera ngay trước mắt.
        const start = initialCameraRef.current;
        if (start) {
          handle.viewer.camera.setView({
            destination: Cartesian3.fromDegrees(
              start.longitude,
              start.latitude,
              zoomToHeight(start.zoom, start.latitude, host.clientHeight || 720),
            ),
            orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
          });
        }

        // Chọn bằng handler riêng thay vì InfoBox của Cesium: bảng chi tiết là
        // component React, để Cesium tự chọn sẽ có hai nguồn sự thật.
        handler = new ScreenSpaceEventHandler(handle.viewer.scene.canvas);
        handler.setInputAction((movement: { position: unknown }) => {
          const picked = handle.viewer.scene.pick(movement.position as never);
          const id = picked?.id?.id as string | undefined;
          const props = picked?.id?.properties?.getValue(JulianDate.now()) as { kind?: string } | undefined;
          if (!id || !props?.kind) {
            pickRef.current.onPickFlow(null);
            pickRef.current.onPickHub(null);
            return;
          }
          if (props.kind === "route") {
            pickRef.current.onPickFlow(id.replace(/^route:/, ""));
            pickRef.current.onPickHub(null);
          } else {
            pickRef.current.onPickHub(id.replace(/^node:/, ""));
            pickRef.current.onPickFlow(null);
          }
        }, ScreenSpaceEventType.LEFT_CLICK);

        setReady(true);
        readyRef.current?.();
      })
      .catch((err: unknown) => {
        console.error("[globe] không dựng được Cesium Viewer:", err);
        // Dọn mọi thứ Cesium đã kịp chèn vào container trước khi ném lỗi. Nếu
        // không, phần DOM dang dở của nó nằm lại phía sau thông báo lỗi của
        // chính chúng ta.
        if (host) host.innerHTML = "";
        setError(err instanceof Error ? err.message : String(err));
      });

    return () => {
      disposed = true;
      handler?.destroy();
      const viewer = viewerRef.current;
      viewerRef.current = null;
      if (viewer && !viewer.isDestroyed()) viewer.destroy();
    };
  }, []);

  // Dữ liệu và bộ lọc: chỉ vẽ lại thực thể, không đụng camera.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!ready || !viewer || viewer.isDestroyed()) return;
    syncScene(viewer, scene, flowSpecs);
    highlight(viewer, selectedFlow, selectedHub);
  }, [ready, scene, flowSpecs, selectedFlow, selectedHub]);

  return (
    <div className="absolute inset-0">
      {/* Cùng lý do với host của MapLibre: widgets.css của Cesium cũng đặt
          `position: relative` lên container mà nó tiếp quản. */}
      <div ref={hostRef} className="absolute inset-0 h-full w-full" data-testid="cesium-host" />

      {!ready && !error && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-meta text-ink-low">
          Đang nạp bản đồ Trái Đất…
        </div>
      )}

      {error && (
        <div className="absolute inset-0 grid place-items-center p-6">
          <div className="max-w-[420px] rounded-control border border-risk/30 bg-risk/10 p-3 text-meta leading-relaxed">
            <div className="mb-1 font-semibold text-risk-soft">Không dựng được bản đồ Trái Đất</div>
            <p className="text-ink-soft">
              Phần còn lại của bảng điều khiển vẫn hoạt động. Chi tiết lỗi nằm ở console trình duyệt.
            </p>
            <p className="mt-1 break-words font-mono text-micro text-ink-low">{error}</p>
          </div>
        </div>
      )}

      {/* Nguồn ảnh là thông tin vận hành: ngoại tuyến nghĩa là thiếu token hoặc
          mất mạng, và độ chi tiết khi zoom sâu sẽ kém hẳn. */}
      {ready && imagery === "offline" && (
        <div className="pointer-events-none absolute bottom-2 right-2 rounded-chip border border-warn/30 bg-warn/10 px-2 py-0.5 text-micro text-warn-soft">
          Ảnh nền ngoại tuyến
        </div>
      )}
    </div>
  );
});
