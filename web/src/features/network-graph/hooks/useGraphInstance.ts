import { useEffect, useRef } from "react";

import type { EngineCallbacks } from "../engine/GraphEngine";
import { GraphEngine } from "../engine/GraphEngine";

/**
 * Vòng đời của engine canvas.
 *
 * Engine được tạo *một lần* cho cả vòng đời màn hình. Mọi thay đổi state sau đó
 * đi qua các setter — đây chính là yêu cầu "không tạo lại instance sau mỗi lần
 * đổi state" ở mục hiệu năng: tạo lại đồng nghĩa mất camera, mất alpha đang
 * chuyển, và một khung hình trắng.
 *
 * Callback được giữ trong ref để engine luôn gọi bản mới nhất mà không cần
 * dựng lại listener.
 */
export function useGraphInstance(
  hostRef: React.RefObject<HTMLDivElement | null>,
  canvasRef: React.RefObject<HTMLCanvasElement | null>,
  tooltipRef: React.RefObject<HTMLDivElement | null>,
  callbacks: EngineCallbacks,
) {
  const engineRef = useRef<GraphEngine | null>(null);
  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    const tooltip = tooltipRef.current;
    if (!host || !canvas || !tooltip) return;

    const engine = new GraphEngine(host, canvas, tooltip);
    engine.setCallbacks({
      onSelectNode: (id) => cbRef.current.onSelectNode?.(id),
      onSelectEdge: (id) => cbRef.current.onSelectEdge?.(id),
      onExpandNode: (id) => cbRef.current.onExpandNode?.(id),
      onZoomLevel: (lvl, z) => cbRef.current.onZoomLevel?.(lvl, z),
      onHover: (id) => cbRef.current.onHover?.(id),
    });
    engineRef.current = engine;

    return () => {
      engine.dispose();
      engineRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return engineRef;
}
