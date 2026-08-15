import type { ReactNode } from "react";

/**
 * Thanh công cụ nằm trên một vùng nội dung.
 *
 * Dùng cho đầu không gian làm việc (đồ thị, bản đồ) và đầu bảng nhiều bộ lọc.
 * Nền `side` để nó thuộc về khung ứng dụng chứ không thuộc về nội dung bên
 * dưới — cùng lý do sidebar và header dùng nền ấy.
 */
export function Toolbar({
  children,
  end,
  className = "",
}: {
  children: ReactNode;
  /** Nhóm bên phải: hành động, chỉ báo trạng thái. */
  end?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`flex flex-none flex-wrap items-center gap-2 border-b border-line bg-side px-3 py-2 ${className}`}
    >
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">{children}</div>
      {end && <div className="flex flex-none flex-wrap items-center gap-2">{end}</div>}
    </div>
  );
}

/** Nhóm control trong thanh công cụ, có nhãn nhỏ phía trước. */
export function ToolbarGroup({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 items-center gap-1.5">
      {label && <span className="whitespace-nowrap text-micro uppercase tracking-[0.08em] text-ink-dim">{label}</span>}
      {children}
    </div>
  );
}
