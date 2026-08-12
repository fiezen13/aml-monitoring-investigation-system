import { useState } from "react";

import type { LayoutKey } from "../types/graph.types";

const LAYOUTS: [LayoutKey, string][] = [
  ["flow", "Investigation Flow"],
  ["force", "Force"],
  ["hierarchy", "Hierarchical"],
  ["community", "Community"],
];

interface Props {
  layout: LayoutKey;
  perf: boolean;
  isolated: boolean;
  story: boolean;
  hasFocus: boolean;
  hops: number;
  nodeCount: number;
  edgeCount: number;
  search: string;
  onSearch: (v: string) => void;
  onLayout: (l: LayoutKey) => void;
  onFit: () => void;
  onExpandHop: (hops: number) => void;
  onMoneyPath: () => void;
  onDetectCycle: () => void;
  onIsolate: (on: boolean) => void;
  onStory: (on: boolean) => void;
  onPerf: (on: boolean) => void;
  onExport: () => void;
  onClearFocus: () => void;
}

function Btn({
  children,
  onClick,
  active,
  title,
}: {
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={[
        "whitespace-nowrap rounded-control border px-2.5 py-1 text-2xs font-medium transition-colors",
        active
          ? "border-primary-line bg-primary-soft text-primary"
          : "border-line bg-sunken text-ink-soft hover:bg-elev hover:text-ink-mid",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

/**
 * Thanh công cụ một hàng.
 *
 * Giữ thấp có chủ đích — mỗi pixel chiều cao ở đây là một pixel mất đi của
 * đồ thị. Các hành động ít dùng (Community, Export, Performance) nằm trong menu
 * tràn.
 */
export function GraphToolbar({
  layout,
  perf,
  isolated,
  story,
  hasFocus,
  hops,
  nodeCount,
  edgeCount,
  search,
  onSearch,
  onLayout,
  onFit,
  onExpandHop,
  onMoneyPath,
  onDetectCycle,
  onIsolate,
  onStory,
  onPerf,
  onExport,
  onClearFocus,
}: Props) {
  const [overflow, setOverflow] = useState(false);

  return (
    <div className="relative flex items-center gap-1.5 border-b border-line bg-side px-3 py-1.5">
      <input
        value={search}
        onChange={(e) => onSearch(e.target.value)}
        placeholder="Tìm node (tên, mã, tài khoản…)"
        aria-label="Tìm node trong đồ thị"
        className="w-52 rounded-control border border-line bg-sunken px-2.5 py-1 text-2xs text-ink-mid outline-none placeholder:text-ink-dim focus:border-primary-line"
      />

      <select
        value={layout}
        onChange={(e) => onLayout(e.target.value as LayoutKey)}
        aria-label="Kiểu bố cục"
        className="rounded-control border border-line bg-sunken px-2 py-1 text-2xs text-ink-mid outline-none focus:border-primary-line"
      >
        {LAYOUTS.map(([k, label]) => (
          <option key={k} value={k}>
            {label}
          </option>
        ))}
      </select>

      <Btn onClick={onFit} title="Đưa toàn bộ đồ thị vào khung nhìn">
        Fit
      </Btn>

      <Btn onClick={() => onExpandHop(hops >= 3 ? 1 : hops + 1)} title="Mở rộng vùng lân cận quanh node đang chọn">
        Expand {hops} hop
      </Btn>

      <Btn onClick={onMoneyPath} title="Xếp hạng các đường đi của tiền">
        Money path
      </Btn>

      <Btn onClick={onDetectCycle} title="Tìm chu trình tiền quay lại chủ thể ban đầu">
        Detect cycle
      </Btn>

      <Btn onClick={() => onIsolate(!isolated)} active={isolated} title="Chỉ giữ mạng lưới đáng ngờ">
        ⚡ Isolate suspicious
      </Btn>

      <Btn
        onClick={() => onStory(!story)}
        active={story}
        title="Chỉ để mạch tiền chính sáng — dùng khi trình bày"
      >
        ▶ Luồng chính
      </Btn>

      {hasFocus && (
        <Btn onClick={onClearFocus} title="Bỏ chọn (ESC)">
          Clear focus
        </Btn>
      )}

      <div className="ml-auto flex items-center gap-2">
        <span className="whitespace-nowrap font-mono text-3xs text-ink-dim">
          {nodeCount} node · {edgeCount} edge
        </span>
        <div className="relative">
          <Btn onClick={() => setOverflow((v) => !v)} active={overflow} title="Thêm">
            ⋯
          </Btn>
          {overflow && (
            <div className="absolute right-0 top-8 z-20 w-52 animate-up rounded-panel border border-line bg-panel p-1.5 shadow-[0_16px_40px_rgba(0,0,0,0.55)]">
              <button
                type="button"
                onClick={() => {
                  onLayout("community");
                  setOverflow(false);
                }}
                className="w-full rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Community view
              </button>
              <button
                type="button"
                onClick={() => onPerf(!perf)}
                className="flex w-full items-center justify-between rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Performance mode
                <span className={perf ? "text-primary" : "text-ink-dim"}>{perf ? "BẬT" : "TẮT"}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onExport();
                  setOverflow(false);
                }}
                className="w-full rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Export JSON
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
