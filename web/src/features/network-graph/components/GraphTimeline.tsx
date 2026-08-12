interface Props {
  value: number;
  playing: boolean;
  onChange: (v: number) => void;
  onPlay: (on: boolean) => void;
}

const PRESETS: [string, number][] = [
  ["1h", 0.12],
  ["6h", 0.3],
  ["24h", 0.55],
  ["7d", 0.8],
  ["30d", 1],
];

/**
 * Thanh thời gian nổi trên đồ thị.
 *
 * Kéo thanh này *không* dựng lại đồ thị: toạ độ layout đã tính sẵn và giữ
 * nguyên, chỉ những đỉnh chưa tồn tại ở mốc đang xem bị lọc khỏi lượt vẽ. Nhờ
 * vậy mạng lưới hiện ra dần đúng theo thứ tự sự kiện thay vì nhảy loạn.
 */
export function GraphTimeline({ value, playing, onChange, onPlay }: Props) {
  return (
    <div className="absolute left-3 top-3 z-[5] flex items-center gap-2 rounded-panel border border-line bg-side/90 px-2.5 py-1.5 backdrop-blur">
      <button
        type="button"
        onClick={() => onPlay(!playing)}
        aria-label={playing ? "Tạm dừng" : "Chạy dòng thời gian"}
        className="flex h-5 w-5 items-center justify-center rounded-full border border-primary-line bg-primary-soft text-[9px] text-primary transition-colors hover:bg-elev"
      >
        {playing ? "❚❚" : "▶"}
      </button>

      <input
        type="range"
        min={0}
        max={100}
        value={Math.round(value * 100)}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        aria-label="Thanh thời gian"
        className="w-40 accent-agent"
      />

      <span className="w-10 font-mono text-3xs text-ink-low">{value >= 1 ? "now" : `${Math.round(value * 100)}%`}</span>

      <div className="flex items-center gap-0.5 border-l border-line pl-2">
        {PRESETS.map(([label, v]) => (
          <button
            key={label}
            type="button"
            onClick={() => onChange(v)}
            className={[
              "rounded px-1.5 py-0.5 text-3xs transition-colors",
              Math.abs(value - v) < 0.02 ? "bg-primary-soft text-primary" : "text-ink-dim hover:text-ink-soft",
            ].join(" ")}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}
