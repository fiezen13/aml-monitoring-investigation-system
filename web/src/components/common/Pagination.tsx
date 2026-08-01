import { ChevronLeft, ChevronRight } from "lucide-react";

interface PaginationProps {
  page: number;
  pageCount: number;
  onChange: (page: number) => void;
  summary?: string;
}

export function Pagination({ page, pageCount, onChange, summary }: PaginationProps) {
  const pages: (number | "...")[] = [];
  for (let p = 1; p <= pageCount; p++) {
    if (p <= 3 || p === pageCount || Math.abs(p - page) <= 1) {
      pages.push(p);
    } else if (pages[pages.length - 1] !== "...") {
      pages.push("...");
    }
  }

  const btn =
    "flex h-7 min-w-7 items-center justify-center rounded-control border border-line px-1.5 text-2xs font-medium transition-colors";

  return (
    <div className="flex items-center justify-between gap-3 px-1 py-2">
      <span className="tabular text-2xs text-ink-mid">{summary}</span>
      <nav className="flex items-center gap-1" aria-label="Phân trang">
        <button
          type="button"
          aria-label="Trang trước"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
          className={`${btn} text-ink-mid hover:text-ink-hi disabled:opacity-30`}
        >
          <ChevronLeft size={13} />
        </button>
        {pages.map((p, i) =>
          p === "..." ? (
            <span key={`gap-${i}`} className="px-1 text-2xs text-ink-low">
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              onClick={() => onChange(p)}
              aria-current={p === page ? "page" : undefined}
              className={`${btn} tabular ${
                p === page
                  ? "border-primary bg-primary text-app"
                  : "text-ink-mid hover:text-ink-hi"
              }`}
            >
              {p}
            </button>
          ),
        )}
        <button
          type="button"
          aria-label="Trang sau"
          disabled={page >= pageCount}
          onClick={() => onChange(page + 1)}
          className={`${btn} text-ink-mid hover:text-ink-hi disabled:opacity-30`}
        >
          <ChevronRight size={13} />
        </button>
      </nav>
    </div>
  );
}
