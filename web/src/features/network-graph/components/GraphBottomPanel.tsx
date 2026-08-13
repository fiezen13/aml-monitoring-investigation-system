import type { ReactNode } from "react";

import { usd } from "../../../api/fcFormat";
import { C } from "../../../design/palette";
import type { BottomTab } from "../stores/graph.store";
import type { GEdge, GraphModel, MoneyPath } from "../types/graph.types";
import { MoneyPathPanel } from "./MoneyPathPanel";

const TABS: [BottomTab, string][] = [
  ["paths", "Đường tiền"],
  ["cycles", "Chu trình"],
  ["transactions", "Giao dịch"],
  ["timeline", "Dòng thời gian"],
  ["evidence", "Bằng chứng"],
];

interface Props {
  tab: BottomTab;
  open: boolean;
  model: GraphModel;
  paths: MoneyPath[];
  cycles: string[][];
  activePathId: string | null;
  selectedNodeId: string | null;
  onTab: (t: BottomTab) => void;
  onOpen: (on: boolean) => void;
  onPickPath: (id: string | null) => void;
  onStepPath: (delta: number) => void;
  missingLinks: number;
  /**
   * Nội dung tab "Giao dịch", do màn hình cha dựng.
   *
   * Panel này thuần trình bày; việc tải giao dịch phụ thuộc vào cạnh/đỉnh nào
   * đang chọn, mà đó là state của màn hình chứ không phải của panel.
   */
  transactions: ReactNode;
}

/**
 * Panel dưới, đồng bộ với thứ đang chọn trên đồ thị.
 *
 * "Đồng bộ" ở đây là bắt buộc: nếu bảng giao dịch vẫn liệt kê cả mạng lưới
 * trong khi analyst đang focus một đỉnh thì hai nửa màn hình nói hai chuyện
 * khác nhau, và bảng trở thành nhiễu.
 */
export function GraphBottomPanel({
  tab,
  open,
  model,
  paths,
  cycles,
  activePathId,
  selectedNodeId,
  onTab,
  onOpen,
  onPickPath,
  onStepPath,
  missingLinks,
  transactions,
}: Props) {
  const activePath = paths.find((p) => p.id === activePathId) ?? null;

  // Phạm vi: đường đang chọn > đỉnh đang chọn > toàn mạng.
  const scopedEdges: GEdge[] = activePath
    ? model.edges.filter((e) => activePath.edgeIds.includes(e.id))
    : selectedNodeId
      ? model.edges.filter((e) => e.s === selectedNodeId || e.t === selectedNodeId)
      : model.edges;

  const scopeLabel = activePath
    ? `đường #${paths.indexOf(activePath) + 1}`
    : selectedNodeId
      ? (model.byId[selectedNodeId]?.label ?? "đỉnh đang chọn")
      : "toàn mạng lưới";

  return (
    <div
      className={[
        // Thấp hơn bản trước 42px: chiều cao ở đây lấy thẳng từ đồ thị, mà đồ
        // thị mới là thứ cần chỗ nhất.
        "flex flex-col border-t border-line bg-side transition-[height] duration-200",
        open ? "h-[176px]" : "h-[32px]",
      ].join(" ")}
    >
      <div className="flex flex-none items-center gap-0.5 border-b border-line px-2">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => onTab(key)}
            aria-selected={tab === key}
            className={[
              "border-b-2 px-2.5 py-1.5 text-2xs transition-colors",
              tab === key ? "border-primary text-ink-hi" : "border-transparent text-ink-low hover:text-ink-mid",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
        <span className="ml-2 truncate font-mono text-3xs text-ink-dim">phạm vi: {scopeLabel}</span>
        <button
          type="button"
          onClick={() => onOpen(!open)}
          aria-label={open ? "Thu gọn bảng dưới" : "Mở bảng dưới"}
          className="ml-auto px-2 py-1 text-2xs text-ink-low hover:text-ink-hi"
        >
          {open ? "▾" : "▴"}
        </button>
      </div>

      {open && (
        <div className="min-h-0 flex-1 overflow-hidden">
          {tab === "paths" && (
            <MoneyPathPanel
              paths={paths}
              activeId={activePathId}
              model={model}
              onPick={onPickPath}
              onStep={onStepPath}
              missingLinks={missingLinks}
            />
          )}

          {tab === "cycles" && (
            <div className="h-full overflow-y-auto px-3 py-2">
              {cycles.length ? (
                <ol className="flex flex-col gap-1">
                  {cycles.map((cyc, i) => (
                    <li
                      key={`${cyc.join("-")}-${i}`}
                      className="flex items-center gap-2 rounded-control border border-warn/25 bg-warn/5 px-2.5 py-1.5 text-2xs"
                    >
                      <span className="font-mono text-warn">#{i + 1}</span>
                      <span className="min-w-0 flex-1 truncate text-ink-mid">
                        {cyc.map((id) => model.byId[id]?.shortLabel ?? id).join(" → ")}
                      </span>
                      <span className="font-mono text-ink-dim">{cyc.length - 1} chặng</span>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-xs text-ink-low">
                  Không phát hiện chu trình nào — tiền không quay lại chủ thể ban đầu trong phạm vi đang xem.
                </p>
              )}
            </div>
          )}

          {/* Tab giao dịch giờ hiển thị GIAO DỊCH THẬT, không phải quan hệ.
              Bản cũ liệt kê `scopedEdges` — tức là các cạnh — dưới tiêu đề
              "Giao dịch", nên analyst không có đường nào đi từ một quan hệ
              xuống tới những lần chuyển khoản làm nên quan hệ đó. */}
          {tab === "transactions" && transactions}

          {tab === "timeline" && (
            <div className="h-full overflow-y-auto px-3 py-2">
              <ol className="flex flex-col gap-1">
                {[...scopedEdges]
                  .sort((a, b) => a.time - b.time)
                  .slice(0, 120)
                  .map((e) => (
                    <li key={e.id} className="flex items-center gap-2 text-2xs">
                      <span className="w-28 flex-none font-mono text-ink-dim">
                        {e.knownFrom.slice(0, 16).replace("T", " ")}
                      </span>
                      <span
                        className="h-1.5 w-1.5 flex-none rounded-full"
                        style={{ background: e.inferred ? C.agent : C.info }}
                      />
                      <span className="min-w-0 flex-1 truncate text-ink-mid">
                        {model.byId[e.s]?.shortLabel ?? e.s} → {model.byId[e.t]?.shortLabel ?? e.t}
                      </span>
                      <span className="tabular flex-none font-mono text-ink-low">
                        {e.amt != null ? usd(e.amt) : e.label}
                      </span>
                    </li>
                  ))}
              </ol>
            </div>
          )}

          {tab === "evidence" && (
            <div className="h-full overflow-y-auto px-3 py-2">
              {scopedEdges.filter((e) => e.inferred).length ? (
                <ul className="flex flex-col gap-1.5">
                  {scopedEdges
                    .filter((e) => e.inferred)
                    .slice(0, 60)
                    .map((e) => (
                      <li key={e.id} className="rounded-control border border-agent/25 bg-agent/5 px-2.5 py-1.5">
                        <div className="flex items-center gap-2 text-2xs">
                          <span className="text-ink-mid">
                            {model.byId[e.s]?.shortLabel ?? e.s} → {model.byId[e.t]?.shortLabel ?? e.t}
                          </span>
                          <span className="ml-auto font-mono text-agent-soft">
                            tin cậy {e.conf != null ? e.conf.toFixed(2) : "—"}
                          </span>
                        </div>
                        <p className="mt-0.5 text-3xs leading-relaxed text-ink-low">{e.logic}</p>
                      </li>
                    ))}
                </ul>
              ) : (
                <p className="text-xs text-ink-low">
                  Trong phạm vi này mọi quan hệ đều là quan sát trực tiếp — không có suy luận nào cần phản biện.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
