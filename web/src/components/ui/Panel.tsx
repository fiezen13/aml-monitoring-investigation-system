import { motion } from "motion/react";
import type { ReactNode } from "react";

import { TEXT } from "../../design/typography";
import { safeVariants, staggerItem, useReduced } from "../../design/motion";

/**
 * Thẻ nội dung — khối cơ bản của toàn console.
 *
 * Hợp nhất hai bản trước đó: `fc/primitives.Panel` (không kẻ dưới tiêu đề,
 * padding 14px, có subtitle) và `common/Panel.Panel` (có kẻ dưới tiêu đề,
 * padding 16px, không subtitle). Giữ đường kẻ của bản `common` — với panel có
 * thanh công cụ hoặc bộ lọc trên đầu, tiêu đề không kẻ sẽ trôi vào nội dung —
 * nhưng cho phép tắt qua `divided={false}` ở những panel chỉ có một dòng tiêu đề
 * ngắn, nơi đường kẻ chỉ thêm nhiễu.
 *
 * `variant`:
 *   panel — mặc định, có viền. Dùng khi thẻ đứng một mình.
 *   quiet — không viền, chỉ khác nền. Dùng khi nhiều thẻ nằm cạnh nhau và mỗi
 *           thẻ một viền sẽ tạo ra một lưới ô vuông thay vì một phân cấp.
 */

interface Props {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  variant?: "panel" | "quiet";
  padded?: boolean;
  divided?: boolean;
  className?: string;
  bodyClassName?: string;
  footer?: ReactNode;
  /** Tham gia hiệu ứng vào theo nhóm của `PageShell`. */
  animate?: boolean;
}

export function Panel({
  title,
  subtitle,
  actions,
  children,
  variant = "panel",
  padded = true,
  divided = true,
  className = "",
  bodyClassName = "",
  footer,
  animate = true,
}: Props) {
  const reduced = useReduced();
  const hasHeader = Boolean(title || actions);
  const surface =
    variant === "quiet"
      ? "rounded-panel bg-panel"
      : "rounded-panel border border-line bg-panel";

  const inner = (
    <>
      {hasHeader && (
        <header
          className={`flex flex-wrap items-start gap-3 px-4 py-2.5 ${
            divided ? "border-b border-line" : "pb-1"
          }`}
        >
          <div className="min-w-0 flex-1">
            {title && <div className={TEXT.h3}>{title}</div>}
            {subtitle && <div className="mt-0.5 text-meta text-ink-low">{subtitle}</div>}
          </div>
          {actions && <div className="flex flex-none flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={`${padded ? "p-4" : ""} ${bodyClassName}`}>{children}</div>
      {footer && <div className="border-t border-line px-4 py-2 text-meta text-ink-low">{footer}</div>}
    </>
  );

  if (!animate) {
    return <section className={`overflow-hidden ${surface} ${className}`}>{inner}</section>;
  }

  return (
    <motion.section
      variants={safeVariants(staggerItem, reduced)}
      className={`overflow-hidden ${surface} ${className}`}
    >
      {inner}
    </motion.section>
  );
}

/** Nhãn nhóm viết hoa, đứng đầu mỗi cụm nội dung trong sidebar và inspector. */
export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`${TEXT.eyebrow} ${className}`}>{children}</div>;
}

/** Tiêu đề của một cụm bên trong panel — nhỏ hơn tiêu đề panel một bậc. */
export function SectionHeader({
  title,
  actions,
  className = "",
}: {
  title: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-2 flex items-center justify-between gap-3 ${className}`}>
      <div className="text-body font-semibold text-ink-hi">{title}</div>
      {actions}
    </div>
  );
}

export function Divider({ className = "" }: { className?: string }) {
  return <hr className={`border-0 border-t border-line ${className}`} />;
}
