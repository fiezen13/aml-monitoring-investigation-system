import { motion } from "motion/react";
import type { ReactNode } from "react";

import { TEXT } from "../../design/typography";
import { safeVariants, staggerContainer, useReduced } from "../../design/motion";

/**
 * Khung trang duy nhất của console.
 *
 * Trước đây mỗi trang tự quyết định padding, bề rộng tối đa và khoảng cách dọc:
 * chín trang dùng `p-4` tràn khung, mười trang dùng `mx-auto max-w-[1280px]`
 * **không có padding nào** nên nội dung dính vào mép header và mép sidebar, và
 * bề rộng tối đa chạy từ 980 tới 1280 tuỳ người viết. Bốn biến thể dưới đây
 * thay thế toàn bộ chuyện đó.
 *
 *   default    — trang danh sách và trang tổng hợp. Có bề rộng tối đa vì dòng
 *                văn bản dài quá 1440px không còn đọc được.
 *   dense      — trang nhiều bảng và biểu đồ, cần hết bề ngang màn hình.
 *   workspace  — không gian điều tra có panel riêng (đồ thị mạng lưới): trang
 *                tự quản lý cuộn bên trong, khung ngoài không cuộn.
 *   fullscreen — bản đồ và các bố cục chạm sát mép bốn phía.
 */

export type PageVariant = "default" | "dense" | "workspace" | "fullscreen";

const SHELL: Record<PageVariant, string> = {
  default: "mx-auto flex w-full max-w-[1440px] flex-col gap-4 p-4 lg:p-5",
  dense: "flex w-full flex-col gap-3.5 p-4",
  workspace: "flex h-full min-w-0 flex-col overflow-hidden",
  fullscreen: "flex h-full min-w-0 flex-col overflow-hidden",
};

interface Props {
  variant?: PageVariant;
  /**
   * Tiêu đề trang. Chỉ truyền khi trang cần nói thêm điều gì đó — header của
   * ứng dụng đã hiển thị tên màn hình rồi, và lặp lại y nguyên chỉ tốn một dòng
   * chiều cao mà không thêm thông tin nào.
   */
  title?: string;
  /** Dòng ngữ cảnh cạnh tiêu đề: nguồn dữ liệu, cửa sổ thời gian, giới hạn. */
  meta?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function PageShell({
  variant = "default",
  title,
  meta,
  subtitle,
  actions,
  children,
  className = "",
}: Props) {
  const reduced = useReduced();
  const hasHeader = Boolean(title || subtitle || actions);

  // Không gian làm việc không có animation vào: chúng giữ camera, lựa chọn và
  // vị trí cuộn giữa các lần điều hướng, và một cú fade toàn khung sẽ phá đúng
  // cảm giác liên tục ấy.
  const animated = variant === "default" || variant === "dense";

  const content = (
    <>
      {hasHeader && (
        <header className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && (
              <div className="flex flex-wrap items-baseline gap-2.5">
                <h1 className={`m-0 ${TEXT.h1}`}>{title}</h1>
                {meta && <span className="text-meta text-ink-low">{meta}</span>}
              </div>
            )}
            {subtitle && <p className="mt-1 max-w-[80ch] text-body text-ink-soft">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-none flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      {children}
    </>
  );

  if (!animated) {
    return <div className={`${SHELL[variant]} ${className}`}>{content}</div>;
  }

  return (
    <motion.div
      variants={safeVariants(staggerContainer, reduced)}
      initial="initial"
      animate="animate"
      className={`${SHELL[variant]} ${className}`}
    >
      {content}
    </motion.div>
  );
}
