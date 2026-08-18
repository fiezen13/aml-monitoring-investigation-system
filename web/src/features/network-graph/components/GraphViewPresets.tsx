import type { PresetKey } from "../types/graph.types";
import { PRESETS } from "../utils/graphStyles";

interface Props {
  value: PresetKey;
  onChange: (key: PresetKey) => void;
}

/**
 * Ba chế độ điều tra chính. Đây là segmented control, không phải bộ lọc layer.
 */
export function GraphViewPresets({ value, onChange }: Props) {
  return (
    <div className="rounded-control border border-line bg-app p-0.5" role="group" aria-label="Chế độ điều tra">
      <div className="flex items-center">
        {PRESETS.map((p) => {
          const on = p.key === value;
          return (
            <button
              key={p.key}
              type="button"
              onClick={() => onChange(p.key)}
              aria-pressed={on}
              title={p.hint}
              className={[
                "min-w-[74px] rounded-[4px] px-2.5 py-1 text-center text-2xs font-semibold transition-colors",
                on ? "bg-primary-soft text-primary shadow-sm" : "text-ink-low hover:bg-elev hover:text-ink-mid",
              ].join(" ")}
            >
              {p.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
