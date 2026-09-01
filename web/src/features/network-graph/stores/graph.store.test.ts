import { describe, expect, it } from "vitest";

import { graphReducer, initialState } from "./graph.store";
import { PRESETS } from "../utils/graphStyles";

describe("investigation graph state", () => {
  it("chỉ có ba primary modes và drawer mặc định thu gọn", () => {
    expect(PRESETS.map((preset) => preset.key)).toEqual(["overview", "flow", "evidence"]);
    expect(initialState().bottomOpen).toBe(false);
  });

  it("Evidence giữ focus, layout và mental map hiện tại", () => {
    const focused = graphReducer(initialState(), { type: "selectNode", id: "collector" });
    const collapsed = { "cluster-a": true };
    const withClusters = graphReducer(focused, { type: "setCollapsed", collapsed });
    const evidence = graphReducer(withClusters, { type: "preset", preset: "evidence", collapsed });

    expect(evidence.layout).toBe(withClusters.layout);
    expect(evidence.focus).toEqual(withClusters.focus);
    expect(evidence.collapsed).toBe(collapsed);
  });

  it("đường được chọn sẵn không tự chiếm chiều cao canvas", () => {
    const state = graphReducer(initialState(), { type: "activePath", id: "path-1" });
    expect(state.activePathId).toBe("path-1");
    expect(state.bottomOpen).toBe(false);
  });

  it("replay hỗ trợ play, pause, step và reset độc lập dữ liệu", () => {
    let state = graphReducer(initialState(), { type: "replayPlay" });
    state = graphReducer(state, { type: "replayStep", index: 2 });
    state = graphReducer(state, { type: "replayPause" });
    expect(state.replayStatus).toBe("paused");
    expect(state.replayIndex).toBe(2);

    state = graphReducer(state, { type: "replayStop" });
    expect(state.replayStatus).toBe("idle");
    expect(state.replayIndex).toBe(0);
  });
});
