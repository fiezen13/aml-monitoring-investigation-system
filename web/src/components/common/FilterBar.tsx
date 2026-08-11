import { Calendar, Download, Filter } from "lucide-react";
import type { ReactNode } from "react";

interface FilterChip {
  id: string;
  label: string;
  active: boolean;
  tone?: "risk" | "primary" | "muted";
  onToggle: (id: string) => void;
}

interface FilterBarProps {
  dateLabel?: string;
  chips?: FilterChip[];
  onAdvanced?: () => void;
  onExport?: () => void;
  trailing?: ReactNode;
}

/** Thanh bộ lọc: khoảng ngày, bộ lọc nâng cao, chip lọc nhanh, xuất báo cáo. */
export function FilterBar({ dateLabel, chips, onAdvanced, onExport, trailing }: FilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-panel border border-line bg-panel px-3 py-2">
      {dateLabel && (
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-control border border-line bg-elev px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-primary/40"
        >
          <Calendar size={12} aria-hidden />
          {dateLabel}
        </button>
      )}
      {onAdvanced && (
        <button
          type="button"
          onClick={onAdvanced}
          className="inline-flex items-center gap-1.5 rounded-control border border-line bg-elev px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-primary/40"
        >
          <Filter size={12} aria-hidden />
          Bộ lọc nâng cao
        </button>
      )}
      {chips && chips.length > 0 && (
        <>
          <span className="mx-1 h-5 w-px bg-line" aria-hidden />
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => chip.onToggle(chip.id)}
              aria-pressed={chip.active}
              className={`rounded-full border px-2.5 py-1 text-2xs font-medium transition-colors ${
                chip.active
                  ? chip.tone === "risk"
                    ? "border-risk/50 bg-risk/15 text-risk"
                    : "border-primary/50 bg-primary-soft text-primary"
                  : "border-line text-ink-mid hover:text-ink-hi"
              }`}
            >
              {chip.label}
            </button>
          ))}
        </>
      )}
      <div className="ml-auto flex items-center gap-2">
        {onExport && (
          <button
            type="button"
            onClick={onExport}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-elev px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-primary/40"
          >
            <Download size={12} aria-hidden />
            Xuất báo cáo
          </button>
        )}
        {trailing}
      </div>
    </div>
  );
}
