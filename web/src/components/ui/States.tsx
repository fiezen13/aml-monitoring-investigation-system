import { FileSearch, RefreshCw, ServerCrash } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./Button";

/**
 * Bốn trạng thái của một khối dữ liệu: đang tải, rỗng, lỗi, và khung xương.
 *
 * Gom vào một chỗ vì trước đây có hai bộ (`fc/primitives.Empty|Skeleton` và
 * `common/States`) với hai ngôn từ, hai cỡ chữ và hai chiều cao khác nhau —
 * người dùng gặp cả hai trong cùng một phiên làm việc.
 *
 * Khung xương giữ đúng chiều cao của nội dung thật để bố cục không nhảy khi dữ
 * liệu về; đó là lý do nó tồn tại, không phải để trang trí lúc chờ.
 */

export function EmptyState({
  title = "Không có dữ liệu",
  detail = "Không tìm thấy bản ghi nào khớp với bộ lọc hiện tại.",
  action,
}: {
  title?: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center">
      <FileSearch size={26} className="text-ink-dim" aria-hidden />
      <div className="text-body font-semibold text-ink-hi">{title}</div>
      <div className="max-w-[42ch] text-meta leading-relaxed text-ink-low">{detail}</div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Lỗi tải dữ liệu",
  detail = "Không thể tải dữ liệu từ máy chủ.",
  onRetry,
}: {
  title?: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-12 text-center" role="alert">
      <ServerCrash size={26} className="text-risk" aria-hidden />
      <div className="text-body font-semibold text-ink-hi">{title}</div>
      <div className="max-w-[42ch] text-meta leading-relaxed text-ink-low">{detail}</div>
      {onRetry && (
        <Button size="sm" onClick={onRetry} icon={<RefreshCw size={12} aria-hidden />} className="mt-1">
          Thử lại
        </Button>
      )}
    </div>
  );
}

/** Khung xương cho bảng — mỗi dòng cao đúng bằng một hàng thật. */
export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-1.5 p-3" aria-busy="true" aria-label="Đang tải dữ liệu">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="h-6 animate-pulse rounded-control bg-elev/60" />
      ))}
    </div>
  );
}

/** Khung xương cho lưới thẻ KPI. */
export function CardSkeleton({ count = 4, height = 84 }: { count?: number; height?: number }) {
  return (
    <>
      {Array.from({ length: count }).map((_, index) => (
        <div
          key={index}
          className="animate-pulse rounded-panel bg-panel"
          style={{ height }}
          aria-hidden
        />
      ))}
    </>
  );
}

/** Khối chờ có nhãn — dùng cho panel toàn khung như bản đồ và đồ thị. */
export function LoadingState({ label = "Đang tải dữ liệu…" }: { label?: string }) {
  return (
    <div className="grid place-items-center gap-2 px-4 py-12 text-center" role="status">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-primary/15 border-t-primary" aria-hidden />
      <span className="text-meta text-ink-low">{label}</span>
    </div>
  );
}
