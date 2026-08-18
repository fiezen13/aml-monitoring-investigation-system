import { useState } from "react";

import type { PresetKey } from "../types/graph.types";
import type { GraphComponent } from "../utils/graphComponents";
import { GraphViewPresets } from "./GraphViewPresets";

interface Props {
  preset: PresetKey;
  perf: boolean;
  isolated: boolean;
  story: boolean;
  hasFocus: boolean;
  hops: number;
  nodeCount: number;
  edgeCount: number;
  search: string;
  networks: GraphComponent[];
  activeNetworkId: string | null;
  filtersOpen: boolean;
  onSearch: (v: string) => void;
  onNetwork: (id: string) => void;
  onPreset: (p: PresetKey) => void;
  onFilters: () => void;
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
  preset,
  perf,
  isolated,
  story,
  hasFocus,
  hops,
  nodeCount,
  edgeCount,
  search,
  networks,
  activeNetworkId,
  filtersOpen,
  onSearch,
  onNetwork,
  onPreset,
  onFilters,
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
    <div className="relative flex min-h-[42px] items-center gap-1.5 border-b border-line bg-side px-3 py-1.5">
      <select
        value={activeNetworkId ?? ""}
        onChange={(event) => onNetwork(event.target.value)}
        aria-label="Chọn mạng lưới giao dịch"
        title="Mỗi lựa chọn là một connected component độc lập"
        className="w-52 rounded-control border border-line bg-sunken px-2 py-1 text-2xs font-medium text-ink-mid outline-none focus:border-primary-line 2xl:w-64"
      >
        {networks.map((network) => (
          <option key={network.id} value={network.id}>
            {network.label} · {network.nodeCount} đỉnh/{network.edgeCount} cạnh
          </option>
        ))}
      </select>

      <GraphViewPresets value={preset} onChange={onPreset} />

      <Btn onClick={() => onExpandHop(hops >= 3 ? 1 : hops + 1)} title="Mở rộng vùng lân cận quanh đỉnh đang chọn">
        Mở rộng 1 hop
      </Btn>

      <Btn onClick={onMoneyPath} title="Xếp hạng các đường đi của tiền">
        Tìm đường tiền
      </Btn>

      <Btn onClick={onDetectCycle} title="Tìm chu trình tiền quay lại chủ thể ban đầu">
        Mẫu hình
      </Btn>

      <Btn onClick={onFilters} active={filtersOpen} title="Mở bộ lọc và lớp dữ liệu">
        Bộ lọc
      </Btn>

      {hasFocus && (
        <Btn onClick={onClearFocus} title="Bỏ chọn (ESC)">
          Bỏ vùng tập trung
        </Btn>
      )}

      <div className="ml-auto flex items-center gap-2">
        <div className="relative hidden xl:block">
          <span className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-dim">⌕</span>
          <input
            value={search}
            onChange={(e) => onSearch(e.target.value)}
            placeholder="Tìm thực thể…"
            aria-label="Tìm đỉnh trong đồ thị"
            className="w-36 rounded-control border border-line bg-sunken py-1 pl-6 pr-2 text-2xs text-ink-mid outline-none placeholder:text-ink-dim focus:border-primary-line 2xl:w-44"
          />
        </div>
        <span className="whitespace-nowrap font-mono text-3xs text-ink-dim">
          {nodeCount} đỉnh · {edgeCount} cạnh
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
                  onFit();
                  setOverflow(false);
                }}
                className="w-full rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Vừa khung và căn giữa
              </button>
              <button
                type="button"
                onClick={() => onIsolate(!isolated)}
                className="flex w-full items-center justify-between rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Cô lập mạng đáng ngờ
                <span className={isolated ? "text-ok" : "text-ink-dim"}>{isolated ? "Bật" : "Tắt"}</span>
              </button>
              <button
                type="button"
                onClick={() => onStory(!story)}
                className="flex w-full items-center justify-between rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Trình bày luồng chính
                <span className={story ? "text-ok" : "text-ink-dim"}>{story ? "Bật" : "Tắt"}</span>
              </button>
              <button
                type="button"
                onClick={() => onPerf(!perf)}
                className="flex w-full items-center justify-between rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Chế độ hiệu năng
                <span className={perf ? "text-ok" : "text-ink-dim"}>{perf ? "Bật" : "Tắt"}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  onExport();
                  setOverflow(false);
                }}
                className="w-full rounded-control px-2 py-1.5 text-left text-2xs text-ink-mid hover:bg-elev"
              >
                Xuất JSON
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
