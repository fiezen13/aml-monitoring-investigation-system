import { useEffect, useRef } from "react";

import type { GraphEngine, RenderGap } from "../engine/GraphEngine";
import { useGraphInstance } from "../hooks/useGraphInstance";
import type { RenderGraph, ZoomLevel } from "../types/graph.types";
import type { Emphasis } from "../utils/graphOpacity";

interface Props {
  graph: RenderGraph;
  emphasis: Emphasis;
  perf: boolean;
  showColumns: boolean;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Tăng lên để yêu cầu engine fit lại khung nhìn. */
  fitNonce: number;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
  onExpandNode: (id: string) => void;
  onZoomLevel: (level: ZoomLevel) => void;
  gaps: RenderGap[];
  engineRef?: (engine: GraphEngine | null) => void;
}

/**
 * Cầu nối React ↔ canvas.
 *
 * Component này cố tình không giữ state nào: nó chỉ đẩy props xuống engine qua
 * các effect nhỏ, mỗi effect một mối quan tâm. Nhờ vậy đổi `emphasis` không kéo
 * theo tính lại layout, và đổi `graph` không làm mất camera.
 */
export function GraphCanvas({
  graph,
  emphasis,
  perf,
  showColumns,
  selectedNodeId,
  selectedEdgeId,
  fitNonce,
  onSelectNode,
  onSelectEdge,
  onExpandNode,
  onZoomLevel,
  gaps,
  engineRef,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const engine = useGraphInstance(hostRef, canvasRef, tooltipRef, {
    onSelectNode,
    onSelectEdge,
    onExpandNode,
    onZoomLevel: (lvl) => onZoomLevel(lvl),
  });

  useEffect(() => {
    engineRef?.(engine.current);
    // Móc đo đạc chỉ có ở bản dev: cho phép kiểm tra bố cục bằng số thật
    // (mức phóng, tỷ lệ đồ thị chiếm khung, đường kính đỉnh tier 1) thay vì
    // chỉ ước lượng bằng mắt. Bản build production không có dòng này.
    if (import.meta.env.DEV) {
      (window as unknown as Record<string, unknown>).__fin07Graph = engine.current;
    }
  }, [engine, engineRef]);

  useEffect(() => {
    engine.current?.setGraph(graph);
  }, [engine, graph]);

  useEffect(() => {
    engine.current?.setEmphasis(emphasis);
  }, [engine, emphasis]);

  useEffect(() => {
    engine.current?.setGaps(gaps);
  }, [engine, gaps]);

  useEffect(() => {
    engine.current?.setOptions({
      perf,
      showColumns,
      showMinimap: true,
      reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    });
  }, [engine, perf, showColumns]);

  useEffect(() => {
    engine.current?.setSelection(selectedNodeId, selectedEdgeId);
  }, [engine, selectedNodeId, selectedEdgeId]);

  useEffect(() => {
    if (fitNonce > 0) engine.current?.fit();
  }, [engine, fitNonce]);

  // Đồ thị lần đầu có dữ liệu thì fit một lần, không đợi người dùng bấm.
  const fittedRef = useRef(false);
  useEffect(() => {
    if (fittedRef.current || !graph.nodes.length) return;
    fittedRef.current = true;
    const id = requestAnimationFrame(() => engine.current?.fit());
    return () => cancelAnimationFrame(id);
  }, [engine, graph.nodes.length]);

  return (
    <div ref={hostRef} className="absolute inset-0 cursor-grab overflow-hidden">
      <canvas ref={canvasRef} className="absolute inset-0 block h-full w-full" />
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute z-10 hidden max-w-[280px] rounded-[9px] border border-line-strong bg-[rgba(10,23,36,0.97)] px-[11px] py-2 text-xs leading-relaxed text-ink-hi shadow-[0_10px_30px_rgba(0,0,0,0.5)]"
      />
    </div>
  );
}
