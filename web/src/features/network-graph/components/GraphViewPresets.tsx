import { Eyebrow } from "../../../components/fc/primitives";
import type { PresetKey } from "../types/graph.types";
import { PRESETS } from "../utils/graphStyles";

interface Props {
  value: PresetKey;
  onChange: (key: PresetKey) => void;
}

/**
 * Năm chế độ xem.
 *
 * Thay cho việc bắt analyst bật/tắt hàng chục checkbox: mỗi preset là một câu
 * hỏi điều tra ("tiền đi đâu", "ai điều khiển ai", "thiết bị nào dùng chung"),
 * và nó đổi thật state của đồ thị chứ không chỉ đổi màu nút.
 */
export function GraphViewPresets({ value, onChange }: Props) {
  const active = PRESETS.find((p) => p.key === value);

  return (
    <div>
      <Eyebrow className="mb-2">Chế độ xem</Eyebrow>
      <div className="grid grid-cols-2 gap-1.5">
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
                "rounded-control border px-2 py-1.5 text-left text-2xs font-medium transition-colors",
                p.key === "overview" ? "col-span-2" : "",
                on
                  ? "border-primary-line bg-primary-soft text-primary"
                  : "border-line bg-sunken text-ink-soft hover:bg-elev hover:text-ink-mid",
              ].join(" ")}
            >
              {p.label}
            </button>
          );
        })}
      </div>
      {active && <p className="mt-2 text-3xs leading-relaxed text-ink-dim">{active.hint}</p>}
    </div>
  );
}
