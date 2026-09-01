import { useMemo } from "react";

import type { GraphModel, Stage } from "../types/graph.types";
import { STAGES, STAGE_LABEL } from "../types/graph.types";

interface Props {
  model: GraphModel | null;
  onPickStage: (nodeId: string) => void;
}

/**
 * Dải điều hướng theo chặng, chỉ hiện ở chế độ trình bày.
 *
 * Không phải wizard: nó không ép thứ tự, không có bước tiếp theo, không giữ
 * trạng thái riêng. Chỉ là tám cái mốc để trong lúc nói chuyện có thể nhảy
 * thẳng tới chặng đang đề cập mà không phải đi tìm đỉnh trên đồ thị.
 */
export function GraphStoryStrip({ model, onPickStage }: Props) {
  const stops = useMemo(() => {
    if (!model) return [];
    return STAGES.map((stage: Stage) => {
      const members = model.nodes.filter((n) => n.stage === stage && !n.negative && n.band === "primary");
      if (!members.length) return null;
      const top = members.reduce((a, b) => (b.risk > a.risk ? b : a));
      return { stage, label: STAGE_LABEL[stage], count: members.length, nodeId: top.id };
    }).filter((s): s is { stage: Stage; label: string; count: number; nodeId: string } => s !== null);
  }, [model]);

  if (stops.length < 2) return null;

  return (
    // Nâng lên trên hàng chú giải: hai lớp nổi cùng ở đáy sẽ đè lên nhau.
    <div className="pointer-events-auto absolute bottom-[62px] left-1/2 z-[6] flex -translate-x-1/2 items-center gap-1 rounded-chip border border-line bg-side/92 px-2 py-1.5 backdrop-blur">
      {stops.map((s, i) => (
        <div key={s.stage} className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => onPickStage(s.nodeId)}
            className="flex items-center gap-1.5 rounded-chip px-2 py-0.5 text-2xs text-ink-mid transition-colors hover:bg-elev hover:text-ink-hi"
          >
            <span className="font-mono text-3xs text-ink-dim">{i + 1}</span>
            {s.label}
            <span className="font-mono text-3xs text-ink-dim">{s.count}</span>
          </button>
          {i < stops.length - 1 && <span className="text-ink-dim">→</span>}
        </div>
      ))}
    </div>
  );
}
