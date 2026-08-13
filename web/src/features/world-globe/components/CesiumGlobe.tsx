import {
  JulianDate,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Viewer,
} from "cesium";
import { useEffect, useMemo, useRef, useState } from "react";

import type { MapData } from "../../../components/fc/WorldMap";
import { buildScene, type FilterState } from "../adapters/toCesium";
import { highlight, syncScene } from "../cesium/layers";
import { createScene, morphTo, type ImagerySource } from "../cesium/scene";

interface Props {
  data: MapData | null;
  /** `map` = 2D, `globe` = 3D. Cùng một Viewer phục vụ cả hai. */
  mode: "map" | "globe";
  layers: Record<string, boolean>;
  sev: string;
  typ: string;
  topN: number;
  hideNormal: boolean;
  selectedFlow: string | null;
  selectedHub: string | null;
  onPickFlow: (id: string | null) => void;
  onPickHub: (id: string | null) => void;
}

/**
 * Quả cầu Trái Đất Cesium mang lớp phủ tình báo AML.
 *
 * Viewer được dựng đúng một lần và sống suốt vòng đời component. Đổi chế độ, đổi
 * bộ lọc hay đổi lựa chọn đều chỉ tác động lên cảnh — không dựng lại Viewer, vì
 * làm vậy sẽ mất camera, mất lựa chọn, và rò rỉ một context WebGL mỗi lần.
 */
export function CesiumGlobe({
  data,
  mode,
  layers,
  sev,
  typ,
  topN,
  hideNormal,
  selectedFlow,
  selectedHub,
  onPickFlow,
  onPickHub,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [ready, setReady] = useState(false);
  const [imagery, setImagery] = useState<ImagerySource | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Giữ callback trong ref: nếu đưa thẳng vào deps của effect gắn sự kiện thì
  // mỗi lần WorldPage render lại sẽ tháo và gắn lại handler của Cesium.
  const pickRef = useRef({ onPickFlow, onPickHub });
  pickRef.current = { onPickFlow, onPickHub };

  const filter = useMemo<FilterState>(
    () => ({ layers, severity: sev, typology: typ, topN, suspiciousOnly: hideNormal }),
    [layers, sev, typ, topN, hideNormal],
  );
  const scene = useMemo(() => buildScene(data, filter), [data, filter]);

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

        // Chọn bằng handler riêng thay vì InfoBox của Cesium: bảng chi tiết là
        // component React, để Cesium tự chọn sẽ có hai nguồn sự thật.
        handler = new ScreenSpaceEventHandler(handle.viewer.scene.canvas);
        handler.setInputAction((movement: { position: unknown }) => {
          const picked = handle.viewer.scene.pick(movement.position as never);
          const id = picked?.id?.id as string | undefined;
          const props = picked?.id?.properties?.getValue(JulianDate.now()) as
            | { kind?: string }
            | undefined;
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
      })
      .catch((err: unknown) => {
        console.error("[globe] không dựng được Cesium Viewer:", err);
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

  // Dữ liệu và bộ lọc: chỉ vẽ lại thực thể, không đụng camera hay chế độ cảnh.
  useEffect(() => {
    const viewer = viewerRef.current;
    if (!ready || !viewer || viewer.isDestroyed()) return;
    syncScene(viewer, scene);
    highlight(viewer, selectedFlow, selectedHub);
  }, [ready, scene, selectedFlow, selectedHub]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!ready || !viewer || viewer.isDestroyed()) return;
    morphTo(viewer, mode);
  }, [ready, mode]);

  return (
    <div className="absolute inset-0">
      <div ref={hostRef} className="absolute inset-0" data-testid="cesium-host" />

      {!ready && !error && (
        <div className="pointer-events-none absolute inset-0 grid place-items-center text-2xs text-ink-low">
          Đang nạp bản đồ Trái Đất…
        </div>
      )}

      {error && (
        <div className="absolute inset-0 grid place-items-center p-6">
          <div className="max-w-[420px] rounded-control border border-risk/30 bg-risk/10 p-3 text-2xs leading-relaxed">
            <div className="mb-1 font-semibold text-risk-soft">Không dựng được bản đồ Trái Đất</div>
            <p className="text-ink-soft">
              Phần còn lại của bảng điều khiển vẫn hoạt động. Chi tiết lỗi nằm ở console trình duyệt.
            </p>
            <p className="mt-1 break-words font-mono text-3xs text-ink-low">{error}</p>
          </div>
        </div>
      )}

      {/* Nguồn ảnh là thông tin vận hành: ngoại tuyến nghĩa là thiếu token hoặc
          mất mạng, và độ chi tiết khi zoom sâu sẽ kém hẳn. */}
      {ready && imagery === "offline" && (
        <div className="pointer-events-none absolute bottom-2 right-2 rounded-chip border border-warn/30 bg-warn/10 px-2 py-0.5 text-3xs text-warn-soft">
          Ảnh nền ngoại tuyến
        </div>
      )}
    </div>
  );
}
