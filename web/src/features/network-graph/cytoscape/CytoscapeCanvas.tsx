import cytoscape, { type Core, type EdgeSingular, type NodeSingular } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";

import type { RenderEdge, RenderGraph, RenderNode, ZoomLevel } from "../types/graph.types";
import type { Emphasis } from "../utils/graphOpacity";
import { buildElements, edgeLabel, type GapLink } from "./elements";
import { layoutFor } from "./layout";
import { buildStylesheet } from "./stylesheet";
import type { LayoutKey } from "../types/graph.types";

// Đăng ký một lần cho cả tiến trình. Gọi hai lần Cytoscape ném cảnh báo và bỏ
// qua lần sau, nhưng ở dev React chạy effect hai lượt nên vẫn phải tự chặn.
let fcoseRegistered = false;
function ensureFcose(): void {
  if (fcoseRegistered) return;
  fcoseRegistered = true;
  cytoscape.use(fcose);
}

/**
 * Ngưỡng semantic zoom (§16).
 *
 * Không phải "phóng to thì chữ to ra" — mà là *mật độ thông tin đổi theo mức
 * phóng*. Nhìn từ xa chỉ thấy thực thể quan trọng và thực thể rủi ro; càng vào
 * gần càng nhiều nhãn xuất hiện.
 */
/**
 * Đệm khi fit, tính bằng pixel màn hình.
 *
 * Thanh thời gian nổi ở trên và chú giải nổi ở dưới nằm *đè* lên canvas, nên
 * vùng thực sự nhìn thấy được hẹp hơn khung. Không trừ ra thì đỉnh ở rìa dưới
 * nằm khuất sau chú giải — đúng lỗi đang thấy ở ảnh chụp đầu tiên.
 */
const FIT_PADDING = 56;
const OVERLAY_TOP = 52;
const OVERLAY_BOTTOM = 72;

const ZOOM_MEDIUM = 0.72;
const ZOOM_CLOSE = 1.25;

function zoomLevelOf(zoom: number): ZoomLevel {
  if (zoom < ZOOM_MEDIUM) return "far";
  if (zoom < ZOOM_CLOSE) return "medium";
  return "close";
}

/**
 * Đỉnh nào được mang nhãn thường trực ở mức chi tiết này (§17).
 *
 * Luật: xa → chỉ tier 1 và rủi ro ≥80; vừa → thêm tier 2; gần → tất cả trừ
 * thực thể đối chứng. Đây là thứ thay thế cho việc bản cũ vẽ nhãn + vai trò +
 * số tiền dưới *mọi* đỉnh.
 */
function shouldLabel(n: NodeSingular, level: ZoomLevel): boolean {
  if (n.hasClass("cluster-parent")) return false;
  const tier = (n.data("tier") as number) ?? 3;
  const risk = (n.data("risk") as number) ?? 0;
  if (level === "close") return true;
  if (level === "medium") return tier <= 2 || risk >= 60;
  return tier === 1 || risk >= 80;
}

/** Fit rồi đẩy khung nhìn xuống để bù phần bị hai lớp nổi che. */
function fitWithOverlays(cy: Core, animate: boolean): void {
  if (!cy.nodes().length) return;
  // `fit` chỉ nhận một đệm duy nhất cho cả bốn phía, mà hai lớp nổi lại che
  // trên và dưới không đều nhau. Cách đúng với API sẵn có: đệm theo trung bình
  // hai lớp để chắc chắn không cắt, rồi trượt khung nhìn bù phần lệch.
  const pad = FIT_PADDING + (OVERLAY_TOP + OVERLAY_BOTTOM) / 2;
  cy.fit(cy.elements(), pad);
  const shift = (OVERLAY_TOP - OVERLAY_BOTTOM) / 2;
  if (animate) cy.animate({ panBy: { x: 0, y: shift } }, { duration: 220 });
  else cy.panBy({ x: 0, y: shift });
}

export interface HoverPayload {
  x: number;
  y: number;
  title: string;
  lines: string[];
}

interface Props {
  graph: RenderGraph;
  emphasis: Emphasis;
  layout: LayoutKey;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  /** Id các cụm đang mở — quyết định compound node nào được dựng. */
  openClusterIds: string[];
  /** Đỉnh và cạnh nằm trên đường tiền đang xem. */
  pathNodeIds: string[];
  pathEdgeIds: string[];
  /** Chỗ đứt bằng chứng, vẽ thành cạnh chấm chấm riêng. */
  gaps: GapLink[];
  /**
   * Analyst đang ở chế độ đọc đường tiền.
   *
   * Tách khỏi `pathEdgeIds` vì màn hình tự chọn đường tiền số 1 ngay khi tải.
   * Nếu để hai thứ là một thì lần đầu vào trang đã thấy cả mạng lưới mờ đi còn
   * 12% — tức là mất luôn cấu trúc, thứ mà §9 nói phải thấy trước tiên.
   */
  pathMode: boolean;
  /** Tăng lên để yêu cầu chạy lại layout. */
  layoutNonce: number;
  /** Tăng lên để yêu cầu fit lại khung nhìn. */
  fitNonce: number;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
  onExpandNode: (id: string) => void;
  onZoomLevel: (level: ZoomLevel) => void;
  /** Nhận instance để component cha thao tác camera (centerOn). */
  cyRef?: (cy: Core | null) => void;
  busy?: boolean;
}

/**
 * Đồ thị điều tra trên Cytoscape.
 *
 * Component này giữ đúng một thứ state của riêng nó: nội dung tooltip. Mọi thứ
 * khác đi một chiều từ props xuống, và mỗi effect lo đúng một mối quan tâm —
 * đổi lựa chọn không kéo theo tính lại layout, đổi bộ lọc không làm mất camera.
 */
export function CytoscapeCanvas({
  graph,
  emphasis,
  layout,
  selectedNodeId,
  selectedEdgeId,
  openClusterIds,
  pathNodeIds,
  pathEdgeIds,
  gaps,
  pathMode,
  layoutNonce,
  fitNonce,
  onSelectNode,
  onSelectEdge,
  onExpandNode,
  onZoomLevel,
  cyRef,
  busy = false,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const cyInstance = useRef<Core | null>(null);
  const [hover, setHover] = useState<HoverPayload | null>(null);
  const [level, setLevel] = useState<ZoomLevel>("medium");

  // Callback đi qua ref để việc component cha render lại không tháo lắp handler
  // của Cytoscape — tháo lắp giữa chừng làm mất cả sự kiện đang xử lý.
  const cb = useRef({ onSelectNode, onSelectEdge, onExpandNode, onZoomLevel });
  cb.current = { onSelectNode, onSelectEdge, onExpandNode, onZoomLevel };
  const cyRefCb = useRef(cyRef);
  cyRefCb.current = cyRef;

  const nodeById = useMemo(() => {
    const m = new Map<string, RenderNode>();
    graph.nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [graph]);

  const edgeById = useMemo(() => {
    const m = new Map<string, RenderEdge>();
    graph.edges.forEach((e) => m.set(e.id, e));
    return m;
  }, [graph]);

  const data = useRef({ nodeById, edgeById });
  data.current = { nodeById, edgeById };

  // --- Khởi tạo, một lần ---------------------------------------------
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    ensureFcose();

    const cy = cytoscape({
      container: host,
      style: buildStylesheet(),
      elements: [],
      minZoom: 0.15,
      maxZoom: 3.5,
      wheelSensitivity: 0.22,
      // Cytoscape tự chọn phần tử khi bấm; ở đây lựa chọn do React quản lý nên
      // tắt hẳn để hai nguồn không đánh nhau.
      autounselectify: true,
      boxSelectionEnabled: false,
    });
    cyInstance.current = cy;

    cy.on("tap", "node", (ev) => {
      const n = ev.target as NodeSingular;
      if (n.hasClass("cluster-parent")) return;
      // Cụm thu gọn: bấm là mở, không phải là chọn. Đây là hành vi §22.
      if (n.data("isCluster")) {
        cb.current.onExpandNode(n.id());
        return;
      }
      cb.current.onSelectNode(n.id());
      cb.current.onSelectEdge(null);
    });

    cy.on("tap", "edge", (ev) => {
      const edge = ev.target as EdgeSingular;
      // Chỗ đứt không phải quan hệ nên không có gì để mở ra xem.
      if (edge.hasClass("evidence-gap")) return;
      cb.current.onSelectEdge(edge.id());
      cb.current.onSelectNode(null);
    });

    // Bấm nền = bỏ chọn. Không reset camera — analyst vừa mất công zoom tới.
    cy.on("tap", (ev) => {
      if (ev.target === cy) {
        cb.current.onSelectNode(null);
        cb.current.onSelectEdge(null);
      }
    });

    const showTip = (ev: cytoscape.EventObject) => {
      const el = ev.target as NodeSingular | EdgeSingular;
      const pos = ev.renderedPosition ?? { x: 0, y: 0 };
      if (el.isNode()) {
        const n = data.current.nodeById.get(el.id());
        if (!n) return;
        el.addClass("hovered");
        setHover({
          x: pos.x,
          y: pos.y,
          title: n.kind === "cluster" ? `${n.label} · ${n.count} thực thể` : n.label,
          lines: [
            n.role || n.type,
            `Điểm rủi ro ${n.risk}`,
            n.kind === "cluster" ? `${n.count} thực thể trong cụm` : n.sub,
          ].filter(Boolean),
        });
      } else if (el.hasClass("evidence-gap")) {
        el.addClass("hovered");
        setHover({
          x: pos.x,
          y: pos.y,
          title: "Chỗ đứt bằng chứng",
          lines: ["Hai chặng này chưa quan sát được liên kết nào", "Không phải một quan hệ"],
        });
      } else {
        const e = data.current.edgeById.get(el.id());
        if (!e) return;
        el.addClass("hovered");
        const currencies = Object.entries(e.amountsByCurrency);
        setHover({
          x: pos.x,
          y: pos.y,
          title: `${data.current.nodeById.get(e.s)?.label ?? e.s} → ${data.current.nodeById.get(e.t)?.label ?? e.t}`,
          lines: [
            e.txCount > 0 ? `${e.txCount} giao dịch` : "Không có giao dịch ngân hàng đứng sau",
            ...currencies.map(([ccy, amount]) => `${amount.toLocaleString("vi-VN")} ${ccy}`),
            e.inferred ? "Quan hệ suy luận" : "Quan hệ quan sát trực tiếp",
          ],
        });
      }
    };

    const hideTip = (ev: cytoscape.EventObject) => {
      (ev.target as NodeSingular | EdgeSingular).removeClass("hovered");
      setHover(null);
    };

    cy.on("mouseover", "node, edge", showTip);
    cy.on("mouseout", "node, edge", hideTip);
    cy.on("mousemove", "node, edge", (ev) => {
      const pos = ev.renderedPosition;
      if (pos) setHover((h) => (h ? { ...h, x: pos.x, y: pos.y } : h));
    });

    let lastLevel: ZoomLevel = zoomLevelOf(cy.zoom());
    cy.on("zoom", () => {
      const next = zoomLevelOf(cy.zoom());
      if (next === lastLevel) return;
      lastLevel = next;
      setLevel(next);
      cb.current.onZoomLevel(next);
    });

    if (import.meta.env.DEV) {
      (window as unknown as Record<string, unknown>).__fin07Cy = cy;
    }

    cyRefCb.current?.(cy);

    return () => {
      cyRefCb.current?.(null);
      cyInstance.current = null;
      cy.destroy();
    };
  }, []);

  // --- Dữ liệu: dựng lại phần tử và chạy layout ------------------------
  const openKey = openClusterIds.join(",");
  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    const clusterLabels = new Map(graph.openClusters.map((c) => [c.id, c.label]));
    const elements = buildElements(graph, {
      openClusterIds: new Set(openClusterIds),
      clusterLabels,
      gaps,
    });

    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
      // Layout theo chặng ghi toạ độ sẵn vào RenderNode; nạp vào Cytoscape
      // trước khi chạy `preset` để nó có cái mà đặt.
      if (layout === "flow" || layout === "hierarchy") {
        cy.nodes().forEach((n) => {
          const src = nodeById.get(n.id());
          if (src) n.position({ x: src.x, y: src.y });
        });
      }
    });

    if (!elements.length) return;
    const run = cy.layout(layoutFor(layout, cy.nodes().length, false));
    run.on("layoutstop", () => fitWithOverlays(cy, false));
    run.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- openKey thay cho mảng
  }, [graph, layout, openKey, gaps]);

  // Chạy lại layout theo yêu cầu (nút sắp xếp lại, mở rộng lân cận).
  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy || layoutNonce <= 0 || !cy.nodes().length) return;
    const run = cy.layout(layoutFor(layout, cy.nodes().length, true));
    run.on("layoutstop", () => fitWithOverlays(cy, true));
    run.run();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy khi nonce đổi
  }, [layoutNonce]);

  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy || fitNonce <= 0 || !cy.nodes().length) return;
    fitWithOverlays(cy, true);
  }, [fitNonce]);

  // --- Nhãn theo mức phóng --------------------------------------------
  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        n.toggleClass("labelled", shouldLabel(n, level));
      });
    });
  }, [level, graph]);

  // --- Lựa chọn, đường tiền, focus ------------------------------------
  const pathNodeKey = pathNodeIds.join(",");
  const pathEdgeKey = pathEdgeIds.join(",");
  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy) return;
    const pathNodes = new Set(pathNodeIds);
    const pathEdges = new Set(pathEdgeIds);

    cy.batch(() => {
      cy.elements().removeClass("selected on-path dimmed neighbour");

      cy.nodes().forEach((n) => {
        n.toggleClass("on-path", pathNodes.has(n.id()));
      });
      cy.edges().forEach((e) => {
        e.toggleClass("on-path", pathEdges.has(e.id()));
      });

      if (selectedNodeId) {
        const node = cy.getElementById(selectedNodeId);
        if (node.nonempty()) {
          node.addClass("selected");
          // 1 chặng quanh đỉnh đang chọn giữ nguyên độ rõ; phần còn lại lùi hẳn
          // xuống nhưng KHÔNG bị xoá — mất bối cảnh thì mất luôn ý nghĩa (§12).
          const near = node.closedNeighborhood();
          near.addClass("neighbour");
          cy.elements().difference(near).addClass("dimmed");
        }
      } else if (selectedEdgeId) {
        const edge = cy.getElementById(selectedEdgeId);
        if (edge.nonempty()) {
          edge.addClass("selected");
          const near = edge.connectedNodes().union(edge);
          near.addClass("neighbour");
          cy.elements().difference(near).addClass("dimmed");
        }
      } else if (pathMode && pathEdges.size) {
        // Chế độ đường tiền: chỉ mạch đang xem nổi lên (§26).
        const onPath = cy.elements(".on-path");
        cy.elements().difference(onPath).addClass("dimmed");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- dùng khoá chuỗi thay mảng
  }, [selectedNodeId, selectedEdgeId, pathNodeKey, pathEdgeKey, pathMode, graph]);

  // --- Làm mờ theo bộ lọc / preset ------------------------------------
  useEffect(() => {
    const cy = cyInstance.current;
    if (!cy || selectedNodeId || selectedEdgeId) return;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const alpha = emphasis.nodeAlpha.get(n.id());
        // `dimmed` do lựa chọn quản lý; ở đây chỉ đặt độ mờ nền của preset.
        if (!n.hasClass("dimmed")) n.style("opacity", alpha ?? 1);
      });
    });
  }, [emphasis, selectedNodeId, selectedEdgeId]);

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div ref={hostRef} className="absolute inset-0" data-testid="cy-host" />

      {busy && (
        <div className="pointer-events-none absolute left-1/2 top-3 z-10 -translate-x-1/2 rounded-chip bg-panel/95 px-3 py-1 text-2xs text-ink-soft shadow-lg">
          Đang mở rộng…
        </div>
      )}

      {hover && (
        <div
          className="pointer-events-none absolute z-20 max-w-[260px] rounded-control border border-line-strong bg-side/97 px-2.5 py-1.5 text-2xs shadow-lg backdrop-blur"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="truncate font-semibold text-ink-hi">{hover.title}</div>
          {hover.lines.map((line) => (
            <div key={line} className="text-ink-soft">
              {line}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export { edgeLabel };
