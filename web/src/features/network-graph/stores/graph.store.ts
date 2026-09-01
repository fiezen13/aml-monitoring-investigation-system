import type { FocusState, LayerKey, LayoutKey, PresetKey } from "../types/graph.types";
import { presetDef } from "../utils/graphStyles";

/**
 * Toàn bộ state của màn hình gom vào một reducer.
 *
 * Lý do không dùng chục `useState` như bản cũ: preset, layer, cụm và focus phụ
 * thuộc lẫn nhau — đổi preset phải kéo theo layer và trạng thái cụm. Với state
 * rời rạc, mỗi lần đổi preset lại phải nhớ gọi đủ bốn setter, và quên một cái
 * là giao diện rơi vào trạng thái không hợp lệ.
 */

export type BottomTab = "paths" | "cycles" | "transactions" | "timeline" | "evidence";
export type InspectorTab = "overview" | "transactions" | "relationships" | "evidence" | "model";
export type ReplayStatus = "idle" | "playing" | "paused";

export interface GraphState {
  preset: PresetKey;
  layout: LayoutKey;
  layers: Record<LayerKey, boolean>;
  /** Kind cạnh bị tắt thủ công ở phần Advanced. */
  mutedKinds: Record<string, boolean>;
  riskMin: number;
  minAmt: number;
  timeT: number;
  timelinePlaying: boolean;
  collapsed: Record<string, boolean>;
  focus: FocusState;
  activePathId: string | null;
  pathSource: string | null;
  pathTarget: string | null;
  perf: boolean;
  showAlternatives: boolean;
  /** Chế độ trình bày mạch chính, dùng khi demo. */
  story: boolean;
  advancedOpen: boolean;
  bottomTab: BottomTab;
  bottomOpen: boolean;
  inspectorTab: InspectorTab;
  suspiciousMin: number;
  replayStatus: ReplayStatus;
  replayIndex: number;
  replaySpeed: 0.5 | 1 | 2;
}

const EMPTY_FOCUS: FocusState = { nodeId: null, edgeId: null, hops: 1, isolated: false };

function layersForPreset(preset: PresetKey): Record<LayerKey, boolean> {
  const def = presetDef(preset);
  const on = new Set(def.layers);
  return {
    money: on.has("money"),
    entity: on.has("entity"),
    device: on.has("device"),
    alert: on.has("alert"),
    case: on.has("case"),
    negative: on.has("negative"),
  };
}

export function initialState(): GraphState {
  return {
    preset: "overview",
    layout: "force",
    layers: layersForPreset("overview"),
    mutedKinds: {},
    riskMin: 0,
    minAmt: 0,
    timeT: 1,
    timelinePlaying: false,
    collapsed: {},
    focus: EMPTY_FOCUS,
    activePathId: null,
    pathSource: null,
    pathTarget: null,
    perf: false,
    showAlternatives: false,
    story: false,
    advancedOpen: false,
    bottomTab: "paths",
    bottomOpen: false,
    inspectorTab: "overview",
    suspiciousMin: 75,
    replayStatus: "idle",
    replayIndex: 0,
    replaySpeed: 1,
  };
}

export type GraphAction =
  | { type: "preset"; preset: PresetKey; collapsed: Record<string, boolean> }
  | { type: "layout"; layout: LayoutKey }
  | { type: "layer"; layer: LayerKey; on: boolean }
  | { type: "kind"; kind: string; muted: boolean }
  | { type: "riskMin"; value: number }
  | { type: "minAmt"; value: number }
  | { type: "timeT"; value: number }
  | { type: "timelinePlay"; on: boolean }
  | { type: "toggleCluster"; id: string }
  | { type: "setCollapsed"; collapsed: Record<string, boolean> }
  | { type: "selectNode"; id: string | null }
  | { type: "selectEdge"; id: string | null }
  | { type: "hops"; value: number }
  | { type: "isolate"; on: boolean }
  | { type: "clearFocus" }
  | { type: "activePath"; id: string | null }
  | { type: "pathEndpoints"; source: string | null; target: string | null }
  | { type: "perf"; on: boolean }
  | { type: "alternatives"; on: boolean }
  | { type: "story"; on: boolean }
  | { type: "advanced"; on: boolean }
  | { type: "bottomTab"; tab: BottomTab }
  | { type: "bottomOpen"; on: boolean }
  | { type: "inspectorTab"; tab: InspectorTab }
  | { type: "replayPlay" }
  | { type: "replayPause" }
  | { type: "replayStop" }
  | { type: "replayStep"; index: number }
  | { type: "replaySpeed"; speed: 0.5 | 1 | 2 };

export function graphReducer(state: GraphState, action: GraphAction): GraphState {
  switch (action.type) {
    case "preset":
      // Mode chỉ đổi cách đọc cùng một vụ việc. Giữ focus và đường tiền để
      // analyst không mất ngữ cảnh khi chuyển sang Evidence.
      return {
        ...state,
        preset: action.preset,
        mutedKinds: {},
        collapsed: action.collapsed,
      };

    case "layout":
      return { ...state, layout: action.layout };

    case "layer":
      return { ...state, layers: { ...state.layers, [action.layer]: action.on } };

    case "kind":
      return { ...state, mutedKinds: { ...state.mutedKinds, [action.kind]: action.muted } };

    case "riskMin":
      return { ...state, riskMin: action.value };

    case "minAmt":
      return { ...state, minAmt: action.value };

    case "timeT":
      return { ...state, timeT: action.value };

    case "timelinePlay":
      return { ...state, timelinePlaying: action.on };

    case "toggleCluster":
      return { ...state, collapsed: { ...state.collapsed, [action.id]: !state.collapsed[action.id] } };

    case "setCollapsed":
      return { ...state, collapsed: action.collapsed };

    case "selectNode":
      return {
        ...state,
        focus: { ...state.focus, nodeId: action.id, edgeId: null },
        inspectorTab: "overview",
      };

    case "selectEdge":
      return { ...state, focus: { ...state.focus, nodeId: null, edgeId: action.id } };

    case "hops":
      return { ...state, focus: { ...state.focus, hops: action.value } };

    case "isolate":
      return { ...state, focus: { ...state.focus, isolated: action.on } };

    case "clearFocus":
      return {
        ...state,
        focus: { ...EMPTY_FOCUS, isolated: state.focus.isolated },
        activePathId: null,
        replayStatus: "idle",
        replayIndex: 0,
      };

    case "activePath":
      return { ...state, activePathId: action.id, replayStatus: "idle", replayIndex: 0 };

    case "pathEndpoints":
      return { ...state, pathSource: action.source, pathTarget: action.target, activePathId: null };

    case "perf":
      return { ...state, perf: action.on };

    case "alternatives":
      return { ...state, showAlternatives: action.on };

    case "story":
      // Không đụng tới focus, đường tiền đang chọn hay camera: bật/tắt chế độ
      // trình bày chỉ đổi cách vẽ, tắt đi là về đúng chỗ đang dở.
      return { ...state, story: action.on };

    case "advanced":
      return { ...state, advancedOpen: action.on };

    case "bottomTab":
      return { ...state, bottomTab: action.tab, bottomOpen: true };

    case "bottomOpen":
      return { ...state, bottomOpen: action.on };

    case "inspectorTab":
      return { ...state, inspectorTab: action.tab };

    case "replayPlay":
      return { ...state, replayStatus: "playing" };

    case "replayPause":
      return { ...state, replayStatus: "paused" };

    case "replayStop":
      return { ...state, replayStatus: "idle", replayIndex: 0 };

    case "replayStep":
      return { ...state, replayIndex: action.index };

    case "replaySpeed":
      return { ...state, replaySpeed: action.speed };

    default:
      return state;
  }
}
