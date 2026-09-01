import type { ReactNode } from "react";

import { TEXT } from "../../design/typography";

/**
 * Tiêu đề trang.
 *
 * Dùng khi tiêu đề nói được điều gì đó mà thanh header của ứng dụng không nói —
 * một cách gọi khác, một dòng mô tả, hoặc một nhóm hành động. Nếu chỉ lặp lại y
 * nguyên tên màn hình đang hiện ở header thì bỏ hẳn component này đi: nó tốn
 * một dòng chiều cao và không thêm thông tin nào.
 *
 * Cỡ chữ là `h2` chứ không phải `h1`: `h1` của màn hình đã nằm ở header ứng
 * dụng, và hai chữ 24px trên cùng một khung nhìn thì không còn cái nào là chính.
 */
interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className={TEXT.h2}>{title}</h2>
        {subtitle && <p className="mt-1 max-w-[80ch] text-body text-ink-soft">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-none flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
