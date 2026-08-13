import { usd } from "../../../api/fcFormat";
import { C } from "../../../design/palette";
import type { GraphModel, MoneyPath } from "../types/graph.types";

interface Props {
  paths: MoneyPath[];
  activeId: string | null;
  model: GraphModel;
  onPick: (id: string | null) => void;
  onStep: (delta: number) => void;
  /** Số chỗ đứt bằng chứng trong mạch điều tra hiện tại. */
  missingLinks: number;
}

/**
 * Bảng xếp hạng đường tiền.
 *
 * Mỗi dòng phải trả lời được "có đáng lần theo không" mà không cần bấm vào:
 * bao nhiêu chặng, bao nhiêu tiền, mất bao lâu, qua mấy kênh, tin được tới đâu.
 */
export function MoneyPathPanel({ paths, activeId, model, onPick, onStep, missingLinks }: Props) {
  if (!paths.length) {
    return (
      <p className="px-3 py-4 text-xs text-ink-low">
        Chưa tìm được đường tiền nào. Thử hạ ngưỡng giá trị tối thiểu, hoặc bật lại lớp Dòng tiền.
      </p>
    );
  }

  const idx = paths.findIndex((p) => p.id === activeId);

  const active = paths.find((p) => p.id === activeId) ?? null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Dòng tóm tắt đường đang chọn: khi trình bày, đây là câu duy nhất cần
          đọc to lên. Chuỗi chặng viết đầy đủ chứ không chỉ hai đầu. */}
      {active && (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-b border-primary-line bg-primary-soft px-3 py-1.5">
          <span className="font-mono text-2xs text-primary">Đường tiền ưu tiên #{paths.indexOf(active) + 1}</span>
          <span className="min-w-0 flex-1 truncate text-2xs text-ink-mid">
            {active.nodeIds.map((id) => model.byId[id]?.shortLabel ?? id).join(" → ")}
          </span>
          <span className="tabular font-mono text-2xs text-primary">{usd(active.amountUsd)}</span>
          <span className="font-mono text-3xs text-ink-low">{active.hops} chặng</span>
          <span className="font-mono text-3xs text-ink-low">
            {active.durationMin > 0 ? `${active.durationMin} phút` : "cùng thời điểm"}
          </span>
          <span className="font-mono text-3xs text-ink-low">tin cậy {active.confidence.toFixed(2)}</span>
          {missingLinks > 0 && (
            <span className="rounded bg-warn/10 px-1.5 py-px font-mono text-3xs text-warn-soft">
              {missingLinks} thiếu liên kết
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 border-b border-line px-3 py-1.5">
        <span className="text-2xs text-ink-low">{paths.length} đường</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => onStep(-1)}
            disabled={idx <= 0}
            className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev disabled:opacity-40"
          >
            ‹ Trước
          </button>
          <button
            type="button"
            onClick={() => onStep(1)}
            disabled={idx >= paths.length - 1}
            className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev disabled:opacity-40"
          >
            Sau ›
          </button>
          {activeId && (
            <button
              type="button"
              onClick={() => onPick(null)}
              className="rounded-control border border-line px-2 py-0.5 text-2xs text-ink-soft transition-colors hover:bg-elev"
            >
              Bỏ chọn
            </button>
          )}
        </div>
      </div>

      <ol className="min-h-0 flex-1 overflow-y-auto">
        {paths.map((p, i) => {
          const on = p.id === activeId;
          const from = model.byId[p.nodeIds[0]];
          const to = model.byId[p.nodeIds[p.nodeIds.length - 1]];
          return (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onPick(on ? null : p.id)}
                className={[
                  "flex w-full items-center gap-3 border-b border-line-faint px-3 py-2 text-left transition-colors",
                  on ? "bg-primary-soft" : "hover:bg-elev",
                ].join(" ")}
              >
                <span className={`font-mono text-2xs ${on ? "text-primary" : "text-ink-dim"}`}>#{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs text-ink-mid">
                    {from?.shortLabel ?? "?"} <span className="text-ink-dim">→</span> {to?.shortLabel ?? "?"}
                  </span>
                  <span className="mt-0.5 block font-mono text-3xs text-ink-low">
                    {p.hops} chặng · {p.channels} kênh · {p.durationMin > 0 ? `${p.durationMin} phút` : "cùng thời điểm"}
                  </span>
                </span>
                <span className="tabular flex-none text-right">
                  <span className="block font-mono text-xs text-primary">{usd(p.amountUsd)}</span>
                  <span
                    className="block font-mono text-3xs"
                    style={{ color: p.confidence >= 0.8 ? C.ok : p.confidence >= 0.6 ? C.warn : C.risk }}
                  >
                    tin cậy {p.confidence.toFixed(2)}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
