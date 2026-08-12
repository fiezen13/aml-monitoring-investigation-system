import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { Eyebrow, PulseDot } from "../../../components/fc/primitives";
import { C } from "../../../design/palette";
import type { GraphEngine } from "../engine/GraphEngine";
import { useGraphModel } from "../hooks/useGraphModel";
import { useGraphTimeline } from "../hooks/useGraphTimeline";
import { useMoneyPaths } from "../hooks/useMoneyPaths";
import { buildLeads } from "../utils/pathRanking";
import { graphReducer, initialState } from "../stores/graph.store";
import type { ZoomLevel } from "../types/graph.types";
import { activeClusters, buildRenderGraph, defaultCollapsed } from "../utils/graphClustering";
import { findEvidenceGaps, investigationHealth } from "../utils/evidenceGaps";
import type { FilterState } from "../utils/graphClustering";
import { applyLayout } from "../utils/graphLayouts";
import { resolveEmphasis } from "../utils/graphOpacity";
import { GraphBottomPanel } from "./GraphBottomPanel";
import { GraphCanvas } from "./GraphCanvas";
import { GraphInvestigationLeads } from "./GraphInvestigationLeads";
import { GraphLayerPanel } from "./GraphLayerPanel";
import { GraphLegend } from "./GraphLegend";
import { GraphTimeline } from "./GraphTimeline";
import { GraphToolbar } from "./GraphToolbar";
import { GraphTopologySummary } from "./GraphTopologySummary";
import { GraphViewPresets } from "./GraphViewPresets";
import { GraphStoryStrip } from "./GraphStoryStrip";
import { EdgeInspector } from "./EdgeInspector";
import { NodeInspector } from "./NodeInspector";

/**
 * Màn hình Network Graph.
 *
 * Điều phối bốn tầng tách biệt: mô hình (API → chặng/cụm), bộ lọc (→ đồ thị
 * render), nhấn mạnh (→ alpha và tầng cạnh), rồi engine vẽ. Mỗi tầng chỉ tính
 * lại khi đầu vào của chính nó đổi — đó là lý do kéo thanh thời gian không làm
 * chạy lại layout, và đổi focus không làm chạy lại gì ngoài alpha.
 */
export function InvestigationGraph() {
  const { model, loading, error } = useGraphModel(600);
  const [state, dispatch] = useReducer(graphReducer, undefined, initialState);
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>("medium");
  const [fitNonce, setFitNonce] = useState(0);
  const [search, setSearch] = useState("");
  // Dưới 1500px, sidebar của ứng dụng cộng hai cột bên đã chiếm quá nửa màn
  // hình và vùng vẽ không còn đủ chỗ cho tám cột chặng. Thu sẵn cột trái ở kích
  // thước đó; người dùng mở lại bằng nút bất cứ lúc nào.
  const [leftOpen, setLeftOpen] = useState(() => window.innerWidth >= 1500);
  const engineRef = useRef<GraphEngine | null>(null);
  const initedRef = useRef(false);

  // Lần đầu có mô hình: thu gọn cụm theo preset mặc định.
  useEffect(() => {
    if (!model || initedRef.current) return;
    initedRef.current = true;
    dispatch({ type: "setCollapsed", collapsed: defaultCollapsed(model.clusters, "overview") });
  }, [model]);

  // Mở hay thu một cụm làm hộp bao đổi hẳn kích thước, nên phải fit lại — nếu
  // không, mở cụm mule ×12 sẽ đẩy nửa đồ thị ra ngoài khung nhìn.
  const collapsedKey = useMemo(() => JSON.stringify(state.collapsed), [state.collapsed]);
  useEffect(() => {
    setFitNonce((n) => n + 1);
  }, [collapsedKey]);

  const filter: FilterState = useMemo(
    () => ({
      preset: state.preset,
      layers: state.layers,
      mutedKinds: state.mutedKinds,
      riskMin: state.riskMin,
      minAmt: state.minAmt,
      timeT: state.timeT,
      collapsed: state.collapsed,
      showAlternatives: state.showAlternatives,
    }),
    [
      state.preset,
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
    const nodeSet = new Set(nodeIds);
    const edgeIds = graph.edges
      .filter((e) => nodeSet.has(e.s) && nodeSet.has(e.t))
      .filter((e) => {
        // Chỉ giữ cạnh nối hai đỉnh liền kề trên đường, tránh tô cả cạnh tắt.
        const i = nodeIds.indexOf(e.s);
        const j = nodeIds.indexOf(e.t);
        return i >= 0 && j >= 0 && Math.abs(i - j) === 1;
      })
      .map((e) => e.id);
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
    engineRef.current?.centerOn(id);
  }, []);

  const handleSelectNode = useCallback(
    (id: string | null) => {
      if (!id) {
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

  const handleExpandNode = useCallback(
    (id: string) => {
      const rn = graph.byId[id];
      if (rn?.kind === "cluster") {
        dispatch({ type: "toggleCluster", id });
        return;
      }
      dispatch({ type: "selectNode", id });
      dispatch({ type: "hops", value: Math.min(3, state.focus.hops + 1) });
    },
    [graph.byId, state.focus.hops],
  );

  const handlePreset = useCallback(
    (preset: Parameters<typeof defaultCollapsed>[1]) => {
      if (!model) return;
      dispatch({ type: "preset", preset, collapsed: defaultCollapsed(model.clusters, preset) });
      setFitNonce((n) => n + 1);
    },
    [model],
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
        layout={state.layout}
        perf={state.perf}
        isolated={state.focus.isolated}
        story={state.story}
        hasFocus={!!state.focus.nodeId || !!state.focus.edgeId || !!state.activePathId}
        hops={state.focus.hops}
        nodeCount={graph.nodes.length}
        edgeCount={graph.edges.length}
        search={search}
        onSearch={handleSearch}
        onLayout={(l) => {
          dispatch({ type: "layout", layout: l });
          setFitNonce((n) => n + 1);
        }}
        onFit={() => setFitNonce((n) => n + 1)}
        onExpandHop={(h) => dispatch({ type: "hops", value: h })}
        onMoneyPath={() => {
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
          <GraphViewPresets value={state.preset} onChange={handlePreset} />
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
              <div className="absolute inset-0 z-10 grid place-items-center text-sm text-ink-low">
                Đang dựng đồ thị…
              </div>
            )}
            {!loading && error && (
              <div className="absolute inset-0 z-10 grid place-items-center px-6 text-center text-sm text-risk-soft">
                {error}
              </div>
            )}
            {!loading && !error && !model && (
              <div className="absolute inset-0 z-10 grid place-items-center px-6 text-center text-sm text-ink-low">
                <div>
                  Chưa có dữ liệu đồ thị.
                  <br />
                  <span className="text-2xs text-ink-dim">
                    Chạy scripts/abm_generate.py để sinh mạng lưới mô phỏng.
                  </span>
                </div>
              </div>
            )}

            <GraphCanvas
              graph={graph}
              emphasis={emphasis}
              perf={state.perf}
              showColumns={state.layout === "flow" || state.layout === "hierarchy"}
              selectedNodeId={state.focus.nodeId}
              selectedEdgeId={state.focus.edgeId}
              fitNonce={fitNonce}
              onSelectNode={handleSelectNode}
              onSelectEdge={(id) => dispatch({ type: "selectEdge", id })}
              onExpandNode={handleExpandNode}
              onZoomLevel={setZoomLevel}
              gaps={renderGaps}
              engineRef={(e) => (engineRef.current = e)}
            />

            {state.story && (
              <GraphStoryStrip
                model={model}
                onPickStage={(nodeId) => {
                  dispatch({ type: "selectNode", id: nodeId });
                  engineRef.current?.centerOn(nodeId);
                }}
              />
            )}

            <GraphTimeline
              value={state.timeT}
              playing={state.timelinePlaying}
              onChange={(v) => dispatch({ type: "timeT", value: v })}
              onPlay={(on) => dispatch({ type: "timelinePlay", on })}
            />

            <div className="pointer-events-none absolute right-3 top-3 z-[5] flex items-center gap-2 rounded-chip border border-line bg-side/85 px-3 py-1 text-2xs backdrop-blur">
              <PulseDot color={state.perf ? C.warn : C.primary} />
              <span className="font-mono tracking-[0.08em] text-primary">
                {graph.nodes.length} node · {graph.edges.length} edge
              </span>
              <span className="font-mono text-ink-dim">
                zoom {zoomLevel === "far" ? "xa" : zoomLevel === "close" ? "gần" : "vừa"}
              </span>
              {state.perf && <span className="font-mono text-warn">PERF</span>}
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
              selectedNodeId={state.focus.nodeId}
              onTab={(t) => dispatch({ type: "bottomTab", tab: t })}
              onOpen={(on) => dispatch({ type: "bottomOpen", on })}
              onPickPath={(id) => dispatch({ type: "activePath", id })}
              onStepPath={handleStepPath}
              onFocusNode={focusNode}
              missingLinks={gaps.length}
            />
          )}
        </div>

        <aside className="flex min-h-0 w-[252px] flex-none flex-col overflow-y-auto border-l border-line bg-side p-2 2xl:w-[316px] 2xl:p-3">
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
              <Eyebrow className="mb-2">Inspector</Eyebrow>
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

          {model && selectedEdge && (
            <EdgeInspector edge={selectedEdge} model={model} onClose={() => dispatch({ type: "clearFocus" })} />
          )}
        </aside>
      </div>
    </div>
  );
}
