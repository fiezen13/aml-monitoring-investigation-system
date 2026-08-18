import type { Core as CyCore } from "cytoscape";

import type { FcTxRow } from "../../../api/client";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { Eyebrow, Inspector, PulseDot } from "../../../components/ui";
import { useEdgeTransactions, type TxScope } from "../hooks/useEdgeTransactions";
import { useGraphModel } from "../hooks/useGraphModel";
import { useGraphTimeline } from "../hooks/useGraphTimeline";
import { useMoneyPaths } from "../hooks/useMoneyPaths";
import { buildLeads } from "../utils/pathRanking";
import { graphReducer, initialState } from "../stores/graph.store";
import type { GraphModel, PresetKey, ZoomLevel } from "../types/graph.types";
import { activeClusters, buildRenderGraph, defaultCollapsed } from "../utils/graphClustering";
import { findEvidenceGaps, investigationHealth } from "../utils/evidenceGaps";
import type { FilterState } from "../utils/graphClustering";
import { applyLayout } from "../utils/graphLayouts";
import { resolveEmphasis } from "../utils/graphOpacity";
import { GraphBottomPanel } from "./GraphBottomPanel";
import { CytoscapeCanvas } from "../cytoscape/CytoscapeCanvas";
import { GraphInvestigationLeads } from "./GraphInvestigationLeads";
import { GraphLayerPanel } from "./GraphLayerPanel";
import { GraphLegend } from "./GraphLegend";
import { GraphTimeline } from "./GraphTimeline";
import { GraphToolbar } from "./GraphToolbar";
import { GraphTopologySummary } from "./GraphTopologySummary";
import { GraphStoryStrip } from "./GraphStoryStrip";
import { EdgeInspector } from "./EdgeInspector";
import { NodeInspector } from "./NodeInspector";
import { TransactionDetail } from "./TransactionDetail";
import { TransactionTable } from "./TransactionTable";

/**
 * Đưa một đỉnh vào giữa khung nhìn mà không đổi mức phóng.
 *
 * Tách khỏi component vì nó là thao tác mệnh lệnh trên camera — không có state
 * nào của React mô tả được "hãy trượt tới chỗ này".
 */
function centerOn(cy: CyCore | null, id: string): void {
  if (!cy) return;
  const node = cy.getElementById(id);
  if (node.nonempty()) cy.animate({ center: { eles: node } }, { duration: 240 });
}

/**
 * Màn hình Network Graph.
 *
 * Điều phối bốn tầng tách biệt: mô hình (API → chặng/cụm), bộ lọc (→ đồ thị
 * render), nhấn mạnh (→ alpha và tầng cạnh), rồi engine vẽ. Mỗi tầng chỉ tính
 * lại khi đầu vào của chính nó đổi — đó là lý do kéo thanh thời gian không làm
 * chạy lại layout, và đổi focus không làm chạy lại gì ngoài alpha.
 */
export function InvestigationGraph() {
  const { model, components, activeComponentId, setActiveComponentId, loading, error, reload } = useGraphModel(600);
  const [state, dispatch] = useReducer(graphReducer, undefined, initialState);
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>("medium");
  const [fitNonce, setFitNonce] = useState(0);
  const [search, setSearch] = useState("");
  // Dưới 1500px, sidebar của ứng dụng cộng hai cột bên đã chiếm quá nửa màn
  // hình và vùng vẽ không còn đủ chỗ cho tám cột chặng. Thu sẵn cột trái ở kích
  // thước đó; người dùng mở lại bằng nút bất cứ lúc nào.
  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth >= 1500);
  // Chỉ giữ tham chiếu tới instance Cytoscape cho thao tác camera; mọi thứ
  // khác đi qua props. `centerOn` là việc duy nhất React không làm được bằng
  // state vì nó là hành vi mệnh lệnh trên khung nhìn.
  const cyRef = useRef<CyCore | null>(null);
  // Tăng lên để yêu cầu chạy lại fCoSE. Chỉ ba việc được phép chạm vào nó: mở
  // cụm, mở rộng lân cận, và nút sắp xếp lại — xem §23.
  const [layoutNonce, setLayoutNonce] = useState(0);
  const relayout = useCallback(() => setLayoutNonce((n) => n + 1), []);
  // Chế độ đọc đường tiền do analyst bật, không phải trạng thái mặc định — xem
  // ghi chú ở prop `pathMode` của CytoscapeCanvas.
  const [pathMode, setPathMode] = useState(false);
  const [selectedTx, setSelectedTx] = useState<FcTxRow | null>(null);
  const modelRef = useRef<GraphModel | null>(null);

  // Mỗi khi chọn một connected component mới, xoá toàn bộ focus/đường tiền
  // của mạng trước và dựng preset độc lập. Không được để highlight của mạng A
  // tồn tại trên canvas của mạng B.
  useEffect(() => {
    if (!model || modelRef.current === model) return;
    modelRef.current = model;
    dispatch({ type: "preset", preset: "overview", collapsed: defaultCollapsed(model.clusters, "overview") });
    setSelectedTx(null);
    setPathMode(false);
    setSearch("");
    setFitNonce((nonce) => nonce + 1);
  }, [model]);

  // Mở hay thu một cụm làm hộp bao đổi hẳn kích thước, nên phải fit lại — nếu
  // không, mở cụm mule ×12 sẽ đẩy nửa đồ thị ra ngoài khung nhìn.
  const collapsedKey = useMemo(() => JSON.stringify(state.collapsed), [state.collapsed]);
  useEffect(() => {
    setFitNonce((n) => n + 1);
  }, [collapsedKey]);

  const filter: FilterState = useMemo(
    () => ({
      // Ba mode dùng cùng dữ liệu; preset chỉ thay cách bố trí/nhấn mạnh.
      // Giữ filter ổn định để chuyển sang Evidence không dựng lại phần tử và
      // không làm mất mental map.
      preset: "overview",
      layers: state.layers,
      mutedKinds: state.mutedKinds,
      riskMin: state.riskMin,
      minAmt: state.minAmt,
      timeT: state.timeT,
      collapsed: state.collapsed,
      showAlternatives: state.showAlternatives,
    }),
    [
      state.layers,
      state.mutedKinds,
      state.riskMin,
      state.minAmt,
      state.timeT,
      state.collapsed,
      state.showAlternatives,
    ],
  );

  const graph = useMemo(() => {
    if (!model) return { nodes: [], edges: [], byId: {}, openClusters: [] };
    const g = buildRenderGraph(model, filter);
    applyLayout(g, state.layout);
    return g;
  }, [model, filter, state.layout]);

  // Cụm đang mở → compound node bao quanh thành viên. Cụm đang đóng đã được
  // buildRenderGraph gộp thành một đỉnh duy nhất nên không cần khung.
  const openClusterIds = useMemo(
    () => graph.openClusters.map((c) => c.id),
    [graph],
  );

  // Chỗ đứt bằng chứng: tính trên mô hình thật, không phụ thuộc bộ lọc — một
  // mắt xích thiếu thì thiếu ở mọi chế độ xem.
  const gaps = useMemo(() => (model ? findEvidenceGaps(model) : []), [model]);
  const health = useMemo(() => (model ? investigationHealth(model, gaps) : null), [model, gaps]);
  const gapStages = useMemo(() => new Set(gaps.flatMap((g) => [g.fromStage, g.toStage])), [gaps]);

  const { paths, cycles } = useMoneyPaths(model, state.pathSource, state.pathTarget);
  const leads = useMemo(() => (model ? buildLeads(model, paths, gapStages) : []), [model, paths, gapStages]);

  /** Quy hai đầu của chỗ đứt về đỉnh đang hiển thị (có thể là cụm thu gọn). */
  const renderGaps = useMemo(() => {
    if (!model) return [];
    const resolve = (id: string) => {
      const n = model.byId[id];
      if (n?.clusterId && graph.byId[n.clusterId]) return n.clusterId;
      if (n?.clusterId && graph.byId[`${n.clusterId}::rest`] && !graph.byId[id]) return `${n.clusterId}::rest`;
      return id;
    };
    return gaps
      .map((gap) => ({ id: gap.id, fromId: resolve(gap.fromNodeId), toId: resolve(gap.toNodeId), gap }))
      .filter((rg) => graph.byId[rg.fromId] && graph.byId[rg.toId]);
  }, [gaps, model, graph]);
  const activePath = useMemo(
    () => paths.find((p) => p.id === state.activePathId) ?? null,
    [paths, state.activePathId],
  );

  // Bật sẵn đường tiền hạng nhất khi vào màn hình.
  //
  // Đây là điều kiện để "nhìn ra dòng tiền chính trong dưới 5 giây": không chọn
  // sẵn thì mọi cạnh tiền nằm cùng một tầng và không đường nào nổi lên. Analyst
  // bỏ chọn bằng ESC hoặc nút Bỏ chọn ở panel dưới.
  const autoPathRef = useRef(false);
  useEffect(() => {
    if (autoPathRef.current || !paths.length) return;
    autoPathRef.current = true;
    dispatch({ type: "activePath", id: paths[0].id });
  }, [paths]);

  /**
   * Đường tiền tìm trên đồ thị thật, nhưng cần tô trên đồ thị đã gộp cụm — nên
   * phải quy các đỉnh của đường về id đang hiển thị.
   */
  const pathOnRender = useMemo(() => {
    if (!activePath || !model) return null;
    const mapId = (id: string) => {
      const n = model.byId[id];
      if (n?.clusterId && graph.byId[n.clusterId]) return n.clusterId;
      return id;
    };
    const nodeIds = [...new Set(activePath.nodeIds.map(mapId))].filter((id) => graph.byId[id]);
    const edgeIds = nodeIds.slice(0, -1).flatMap((source, index) => {
      const target = nodeIds[index + 1];
      const edge = graph.edges.find((candidate) => candidate.s === source && candidate.t === target);
      return edge ? [edge.id] : [];
    });
    return { ...activePath, nodeIds, edgeIds };
  }, [activePath, model, graph]);

  const emphasis = useMemo(
    () =>
      resolveEmphasis({
        graph,
        preset: state.preset,
        focus: state.focus,
        activePath: pathOnRender,
        showAlternatives: state.showAlternatives,
        suspiciousMin: state.suspiciousMin,
        story: state.story,
      }),
    [graph, state.preset, state.focus, pathOnRender, state.showAlternatives, state.suspiciousMin, state.story],
  );

  useGraphTimeline(
    state.timelinePlaying,
    state.timeT,
    useCallback((v: number) => dispatch({ type: "timeT", value: v }), []),
    useCallback(() => dispatch({ type: "timelinePlay", on: false }), []),
  );

  // Replay đổi đúng một cạnh mỗi bước; animation của nét chạy nằm hoàn toàn
  // trong Cytoscape, React chỉ điều phối nhịp 0.5×/1×/2×.
  useEffect(() => {
    if (state.replayStatus !== "playing") return;
    const edgeCount = pathOnRender?.edgeIds.length ?? 0;
    if (!edgeCount) {
      dispatch({ type: "replayStop" });
      return;
    }
    const timer = window.setTimeout(() => {
      if (state.replayIndex >= edgeCount - 1) dispatch({ type: "replayStop" });
      else dispatch({ type: "replayStep", index: state.replayIndex + 1 });
    }, 900 / state.replaySpeed);
    return () => window.clearTimeout(timer);
  }, [state.replayStatus, state.replayIndex, state.replaySpeed, pathOnRender]);

  // ESC bỏ focus. Đăng ký ở window vì canvas không nhận được phím.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") dispatch({ type: "clearFocus" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const focusNode = useCallback((id: string) => {
    dispatch({ type: "selectNode", id });
    centerOn(cyRef.current, id);
  }, []);

  const handleSelectNode = useCallback(
    (id: string | null) => {
      if (!id) {
        setPathMode(false);
        dispatch({ type: "clearFocus" });
        return;
      }
      const rn = graph.byId[id];
      // Bấm vào cụm thu gọn thì mở cụm ra, đó là hành vi mong đợi hơn là chọn nó.
      if (rn?.kind === "cluster") {
        dispatch({ type: "toggleCluster", id });
        return;
      }
      dispatch({ type: "selectNode", id });
    },
    [graph.byId],
  );

  // --- Tầng giao dịch -------------------------------------------------
  // Phạm vi: cạnh đang chọn > đỉnh đang chọn > không có gì. Không mặc định
  // liệt kê cả mạng lưới — bảng vài nghìn dòng không trả lời được câu hỏi nào.
  const txScope: TxScope = useMemo(() => {
    if (state.focus.edgeId) {
      const re = graph.edges.find((e) => e.id === state.focus.edgeId);
      // Cạnh gộp (hai đầu là cụm thu gọn) không tương ứng với một quan hệ nào
      // trong sổ cái, nên không hỏi được. Mở cụm ra mới truy được.
      if (re?.ref) return { kind: "edge", id: re.ref.id };
      return { kind: "none" };
    }
    if (state.focus.nodeId) {
      const rn = graph.byId[state.focus.nodeId];
      if (rn?.kind === "node") return { kind: "node", id: state.focus.nodeId };
      return { kind: "none" };
    }
    return { kind: "none" };
  }, [state.focus.edgeId, state.focus.nodeId, graph]);

  const tx = useEdgeTransactions(txScope);

  useEffect(() => {
    setSelectedTx(null);
    // Chọn một quan hệ hay một thực thể thì câu hỏi tiếp theo gần như luôn là
    // "gồm những giao dịch nào" — mở sẵn đúng tab đó (§31).
    if (txScope.kind !== "none") dispatch({ type: "bottomTab", tab: "transactions" });
  }, [txScope]);

  const selectedRenderEdge = useMemo(
    () => graph.edges.find((e) => e.id === state.focus.edgeId) ?? null,
    [graph.edges, state.focus.edgeId],
  );

  const txScopeLabel = useMemo(() => {
    if (selectedRenderEdge) {
      const a = model?.byId[selectedRenderEdge.s]?.label ?? graph.byId[selectedRenderEdge.s]?.label ?? selectedRenderEdge.s;
      const b = model?.byId[selectedRenderEdge.t]?.label ?? graph.byId[selectedRenderEdge.t]?.label ?? selectedRenderEdge.t;
      return `${a} → ${b}`;
    }
    if (state.focus.nodeId) return graph.byId[state.focus.nodeId]?.label ?? state.focus.nodeId;
    return "Chưa chọn quan hệ nào";
  }, [selectedRenderEdge, state.focus.nodeId, graph, model]);

  const handleExpandNode = useCallback(
    (id: string) => {
      const rn = graph.byId[id];
      if (rn?.kind === "cluster") {
        dispatch({ type: "toggleCluster", id });
        // Cụm vừa mở ra thêm N đỉnh vào chỗ trước đó chỉ có một — không xếp lại
        // thì chúng chồng lên nhau và lên cả các đỉnh xung quanh.
        relayout();
        return;
      }
      dispatch({ type: "selectNode", id });
      dispatch({ type: "hops", value: Math.min(3, state.focus.hops + 1) });
    },
    [graph.byId, state.focus.hops, relayout],
  );

  const handlePreset = useCallback(
    (preset: PresetKey) => {
      if (!model) return;
      dispatch({ type: "preset", preset, collapsed: state.collapsed });
      // Evidence là lớp đọc chứng cứ trên đúng bố cục hiện tại. Overview và
      // Flow mới thay cấu trúc không gian, nên chỉ hai mode đó được relayout.
      if (preset === "evidence") return;
      dispatch({ type: "layout", layout: preset === "flow" ? "flow" : "force" });
      relayout();
    },
    [model, state.collapsed, relayout],
  );

  const handleSearch = useCallback(
    (v: string) => {
      setSearch(v);
      const q = v.trim().toLowerCase();
      if (q.length < 2 || !model) return;
      const hit = model.nodes.find(
        (n) => n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q) || n.sub.toLowerCase().includes(q),
      );
      if (!hit) return;
      // Node nằm trong cụm đang đóng thì mở cụm ra, nếu không sẽ focus vào hư vô.
      if (hit.clusterId && state.collapsed[hit.clusterId]) {
        dispatch({ type: "toggleCluster", id: hit.clusterId });
      }
      focusNode(hit.id);
    },
    [model, state.collapsed, focusNode],
  );

  const handleExport = useCallback(() => {
    const payload = {
      preset: state.preset,
      layout: state.layout,
      nodes: graph.nodes.map((n) => ({ id: n.id, label: n.label, stage: n.stage, tier: n.tier, risk: n.risk })),
      edges: graph.edges.map((e) => ({ s: e.s, t: e.t, kind: e.kind, amt: e.amt, count: e.count })),
      paths: paths.map((p) => ({ hops: p.hops, amountUsd: p.amountUsd, confidence: p.confidence })),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `fin07-network-${state.preset}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [graph, paths, state.preset, state.layout]);

  const handleStepPath = useCallback(
    (delta: number) => {
      if (!paths.length) return;
      const idx = paths.findIndex((p) => p.id === state.activePathId);
      const next = Math.max(0, Math.min(paths.length - 1, (idx < 0 ? 0 : idx) + delta));
      dispatch({ type: "activePath", id: paths[next].id });
    },
    [paths, state.activePathId],
  );

  const clusters = useMemo(() => (model ? activeClusters(model, filter) : []), [model, filter]);

  const selectedNode = state.focus.nodeId && model ? (model.byId[state.focus.nodeId] ?? null) : null;
  const selectedEdge = state.focus.edgeId ? (graph.edges.find((e) => e.id === state.focus.edgeId) ?? null) : null;

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      <GraphToolbar
        preset={state.preset}
        perf={state.perf}
        isolated={state.focus.isolated}
        story={state.story}
        hasFocus={!!state.focus.nodeId || !!state.focus.edgeId || !!state.activePathId}
        hops={state.focus.hops}
        nodeCount={graph.nodes.length}
        edgeCount={graph.edges.length}
        search={search}
        networks={components}
        activeNetworkId={activeComponentId}
        filtersOpen={leftOpen}
        onSearch={handleSearch}
        onNetwork={setActiveComponentId}
        onPreset={handlePreset}
        onFilters={() => setLeftOpen((open) => !open)}
        onFit={() => setFitNonce((n) => n + 1)}
        onExpandHop={(h) => dispatch({ type: "hops", value: h })}
        onMoneyPath={() => {
          setPathMode(true);
          dispatch({ type: "bottomTab", tab: "paths" });
          if (!state.activePathId && paths.length) dispatch({ type: "activePath", id: paths[0].id });
        }}
        onDetectCycle={() => dispatch({ type: "bottomTab", tab: "cycles" })}
        onIsolate={(on) => dispatch({ type: "isolate", on })}
        onStory={(on) => dispatch({ type: "story", on })}
        onPerf={(on) => dispatch({ type: "perf", on })}
        onExport={handleExport}
        onClearFocus={() => dispatch({ type: "clearFocus" })}
      />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Bề rộng bám theo màn hình: dưới 1536px hai cột bên ăn mất quá nhiều
            chỗ và vùng vẽ bị bóp còn hơn một nửa. */}
        {!leftOpen && (
          <div className="flex w-8 flex-none flex-col items-center border-r border-line bg-side pt-2">
            <button
              type="button"
              onClick={() => setLeftOpen(true)}
              title="Mở bảng bộ lọc"
              aria-label="Mở bảng bộ lọc"
              className="rounded-control px-1.5 py-1 text-2xs text-ink-low transition-colors hover:bg-elev hover:text-ink-hi"
            >
              »
            </button>
          </div>
        )}

        <aside
          className={[
            "flex-col gap-3 overflow-y-auto border-r border-line bg-side p-2 2xl:p-3",
            leftOpen ? "flex w-[208px] flex-none 2xl:w-[268px]" : "hidden",
          ].join(" ")}
        >
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setLeftOpen(false)}
              title="Thu gọn bảng bộ lọc"
              aria-label="Thu gọn bảng bộ lọc"
              className="rounded-control px-1.5 text-2xs text-ink-dim transition-colors hover:bg-elev hover:text-ink-hi"
            >
              «
            </button>
          </div>
          <GraphLayerPanel
            layers={state.layers}
            mutedKinds={state.mutedKinds}
            advancedOpen={state.advancedOpen}
            clusters={clusters}
            collapsed={state.collapsed}
            riskMin={state.riskMin}
            minAmt={state.minAmt}
            showAlternatives={state.showAlternatives}
            onLayer={(layer, on) => dispatch({ type: "layer", layer, on })}
            onKind={(kind, muted) => dispatch({ type: "kind", kind, muted })}
            onAdvanced={(on) => dispatch({ type: "advanced", on })}
            onToggleCluster={(id) => dispatch({ type: "toggleCluster", id })}
            onRiskMin={(v) => dispatch({ type: "riskMin", value: v })}
            onMinAmt={(v) => dispatch({ type: "minAmt", value: v })}
            onAlternatives={(on) => dispatch({ type: "alternatives", on })}
          />
        </aside>

        <div className="flex min-w-[360px] flex-1 flex-col overflow-hidden">
          <div className="relative min-h-0 flex-1 bg-app">
            {loading && (
              <div className="absolute inset-0 z-10 grid place-items-center bg-app/80 backdrop-blur-[1px]">
                <div className="w-64 rounded-panel border border-line bg-side px-4 py-3 shadow-xl">
                  <div className="flex items-center gap-2 text-sm text-ink-mid">
                    <PulseDot tone="primary" />
                    Đang tải mạng lưới…
                  </div>
                  <div className="mt-3 space-y-1.5 text-2xs text-ink-dim">
                    <div className="h-1.5 w-full animate-pulse rounded-full bg-elev" />
                    <p>Đang nhận diện thực thể và dựng quan hệ</p>
                  </div>
                </div>
              </div>
            )}
            {!loading && error && (
              <div className="absolute inset-0 z-10 grid place-items-center bg-app px-6 text-center">
                <div className="max-w-md rounded-panel border border-risk/25 bg-side px-5 py-4">
                  <p className="text-sm font-semibold text-ink-hi">Không tải được mạng lưới.</p>
                  <p className="mt-1 text-xs leading-relaxed text-risk-soft">{error}</p>
                  <button
                    type="button"
                    onClick={reload}
                    className="mt-3 rounded-control border border-primary-line bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary hover:bg-elev"
                  >
                    Thử lại
                  </button>
                </div>
              </div>
            )}
            {!loading && !error && !model && (
              <div className="absolute inset-0 z-10 grid place-items-center bg-app px-6 text-center">
                <div className="max-w-md rounded-panel border border-line bg-side px-5 py-4">
                  <p className="text-sm font-semibold text-ink-hi">Không đủ quan hệ để dựng mạng lưới.</p>
                  <p className="mt-1 text-xs leading-relaxed text-ink-low">
                    Khoảng dữ liệu hiện tại chưa có quan hệ phù hợp với bộ lọc đang dùng.
                  </p>
                  <div className="mt-3 flex justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        dispatch({ type: "riskMin", value: 0 });
                        dispatch({ type: "minAmt", value: 0 });
                      }}
                      className="rounded-control border border-line bg-sunken px-3 py-1.5 text-xs text-ink-mid hover:bg-elev"
                    >
                      Bỏ bộ lọc
                    </button>
                    <button
                      type="button"
                      onClick={reload}
                      className="rounded-control border border-primary-line bg-primary-soft px-3 py-1.5 text-xs font-medium text-primary hover:bg-elev"
                    >
                      Tải lại dữ liệu
                    </button>
                  </div>
                </div>
              </div>
            )}

            <CytoscapeCanvas
              graph={graph}
              emphasis={emphasis}
              layout={state.layout}
              mode={state.preset}
              selectedNodeId={state.focus.nodeId}
              selectedEdgeId={state.focus.edgeId}
              openClusterIds={openClusterIds}
              pathNodeIds={pathOnRender?.nodeIds ?? []}
              pathEdgeIds={pathOnRender?.edgeIds ?? []}
              gaps={renderGaps}
              pathMode={pathMode}
              replayEdgeId={
                state.replayStatus === "idle" ? null : (pathOnRender?.edgeIds[state.replayIndex] ?? null)
              }
              replayNodeId={
                state.replayStatus === "idle" ? null : (pathOnRender?.nodeIds[state.replayIndex + 1] ?? null)
              }
              layoutNonce={layoutNonce}
              fitNonce={fitNonce}
              onSelectNode={handleSelectNode}
              onSelectEdge={(id) => dispatch({ type: "selectEdge", id })}
              onExpandNode={handleExpandNode}
              onZoomLevel={setZoomLevel}
              cyRef={(cy) => (cyRef.current = cy)}
            />

            {state.story && (
              <GraphStoryStrip
                model={model}
                onPickStage={(nodeId) => {
                  dispatch({ type: "selectNode", id: nodeId });
                  centerOn(cyRef.current, nodeId);
                }}
              />
            )}

            <GraphTimeline
              value={state.timeT}
              playing={state.timelinePlaying}
              onChange={(v) => dispatch({ type: "timeT", value: v })}
              onPlay={(on) => dispatch({ type: "timelinePlay", on })}
            />

            <div className="pointer-events-none absolute right-3 top-3 z-hud flex items-center gap-2 rounded-chip border border-line-strong bg-raised/85 px-3 py-1 text-meta backdrop-blur">
              <PulseDot tone={state.perf ? "warn" : "primary"} />
              <span className="font-mono tracking-[0.08em] text-primary">
                {graph.nodes.length} đỉnh · {graph.edges.length} cạnh
              </span>
              <span className="font-mono text-ink-dim">
                thu phóng {zoomLevel === "far" ? "xa" : zoomLevel === "close" ? "gần" : "vừa"}
              </span>
              {state.perf && <span className="font-mono text-warn">HIỆU NĂNG</span>}
            </div>

            {!state.perf && <GraphLegend />}
          </div>

          {model && (
            <GraphBottomPanel
              tab={state.bottomTab}
              open={state.bottomOpen}
              model={model}
              paths={paths}
              cycles={cycles}
              activePathId={state.activePathId}
              transactions={
                <TransactionTable
                  rows={tx.rows}
                  total={tx.total}
                  page={tx.page}
                  pageSize={tx.pageSize}
                  loading={tx.loading}
                  error={tx.error}
                  scopeLabel={txScopeLabel}
                  hasScope={txScope.kind !== "none"}
                  amountsByCurrency={selectedRenderEdge?.amountsByCurrency ?? {}}
                  selectedId={selectedTx?.id ?? null}
                  onPick={setSelectedTx}
                  onPage={tx.setPage}
                />
              }
              selectedNodeId={state.focus.nodeId}
              onTab={(t) => dispatch({ type: "bottomTab", tab: t })}
              onOpen={(on) => dispatch({ type: "bottomOpen", on })}
              onPickPath={(id) => {
                setPathMode(true);
                dispatch({ type: "activePath", id });
              }}
              onStepPath={handleStepPath}
              missingLinks={gaps.length}
              replayStatus={state.replayStatus}
              replayIndex={state.replayIndex}
              replaySpeed={state.replaySpeed}
              onReplay={() => dispatch({ type: "replayPlay" })}
              onPauseReplay={() => dispatch({ type: "replayPause" })}
              onRestartReplay={() => {
                dispatch({ type: "replayStep", index: 0 });
                dispatch({ type: "replayPlay" });
              }}
              onReplaySpeed={(speed) => dispatch({ type: "replaySpeed", speed })}
            />
          )}
        </div>

        {/* Bảng thanh tra. Nội dung trượt vào lại mỗi khi đối tượng đang xem
            đổi — đó là tín hiệu duy nhất cho biết cột bên phải vừa nói về một
            thực thể khác, vì bố cục của nó thì không đổi. */}
        <aside className="flex min-h-0 w-[252px] flex-none flex-col overflow-y-auto border-l border-line bg-side p-2 2xl:w-[316px] 2xl:p-3">
          <Inspector animateKey={selectedNode?.id ?? selectedEdge?.id ?? (selectedTx ? String(selectedTx.id) : null) ?? "overview"}>
          {model && health && !selectedNode && !selectedEdge && (
            <>
              <GraphTopologySummary
                model={model}
                graph={graph}
                paths={paths}
                cycles={cycles}
                health={health}
                onOpenQuestions={() => dispatch({ type: "bottomTab", tab: "evidence" })}
              />
              <GraphInvestigationLeads
                leads={leads}
                onPick={(lead) => {
                  if (lead.nodeId) focusNode(lead.nodeId);
                  if (lead.pathId) dispatch({ type: "activePath", id: lead.pathId });
                }}
              />
              <p className="mt-4 text-3xs leading-relaxed text-ink-dim">
                Quan hệ vẽ nét đứt là quan hệ do mô hình suy ra, không phải quan sát trực tiếp. Mỗi cạnh như vậy đều
                kèm độ tin cậy và diễn giải — đọc chúng trước khi dùng làm căn cứ.
              </p>
            </>
          )}

          {!model && !loading && (
            <div className="text-sm leading-relaxed text-ink-low">
              <Eyebrow className="mb-2">Thanh tra</Eyebrow>
              Chưa có dữ liệu để kiểm tra.
            </div>
          )}

          {model && selectedNode && (
            <NodeInspector
              node={selectedNode}
              model={model}
              tab={state.inspectorTab}
              onTab={(t) => dispatch({ type: "inspectorTab", tab: t })}
              onClose={() => dispatch({ type: "clearFocus" })}
              onExpand={() => dispatch({ type: "hops", value: state.focus.hops >= 3 ? 1 : state.focus.hops + 1 })}
              onFindPath={() => {
                dispatch({ type: "pathEndpoints", source: selectedNode.id, target: null });
                dispatch({ type: "bottomTab", tab: "paths" });
              }}
              onIsolate={() => dispatch({ type: "isolate", on: !state.focus.isolated })}
            />
          )}

          {model && selectedTx && (
            <TransactionDetail
              tx={selectedTx}
              fromLabel={selectedTx.from_account}
              toLabel={selectedTx.to_account}
              onClose={() => setSelectedTx(null)}
              onHighlight={() => {
                // Vòng khép kín: từ một giao dịch quay ngược lên đúng quan hệ
                // sinh ra nó, rồi đưa quan hệ đó vào giữa khung nhìn.
                if (!selectedRenderEdge) return;
                dispatch({ type: "selectEdge", id: selectedRenderEdge.id });
                centerOn(cyRef.current, selectedRenderEdge.s);
              }}
            />
          )}

          {model && selectedEdge && !selectedTx && (
            <EdgeInspector edge={selectedEdge} model={model} onClose={() => dispatch({ type: "clearFocus" })} />
          )}
          </Inspector>
        </aside>
      </div>
    </div>
  );
}
