import { FileSearch, RefreshCw, ServerCrash } from "lucide-react";

/** Skeleton loading — dùng cho bảng và panel khi mô phỏng tải dữ liệu. */
export function LoadingSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true" aria-label="Đang tải dữ liệu">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <div className="h-8 w-8 animate-pulse rounded-full bg-elev" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-2/3 animate-pulse rounded bg-elev" />
            <div className="h-2.5 w-1/3 animate-pulse rounded bg-elev" />
          </div>
          <div className="h-5 w-16 animate-pulse rounded bg-elev" />
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title = "Không có dữ liệu",
  detail = "Không tìm thấy bản ghi nào khớp với bộ lọc hiện tại.",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <FileSearch size={28} className="text-ink-low" aria-hidden />
      <div className="text-[13px] font-semibold text-ink-hi">{title}</div>
      <div className="max-w-xs text-2xs text-ink-mid">{detail}</div>
    </div>
  );
}

export function ErrorState({
  detail = "Không thể tải dữ liệu từ máy chủ. Vui lòng thử lại.",
  onRetry,
}: {
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <ServerCrash size={28} className="text-risk" aria-hidden />
      <div className="text-[13px] font-semibold text-ink-hi">Lỗi tải dữ liệu</div>
      <div className="max-w-xs text-2xs text-ink-mid">{detail}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2 inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-2xs font-medium text-ink-hi hover:border-primary/50"
        >
          <RefreshCw size={12} aria-hidden />
          Thử lại
        </button>
      )}
    </div>
  );
}
