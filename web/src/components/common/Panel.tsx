import type { ReactNode } from "react";

import { Panel as UiPanel } from "../ui/Panel";

/**
 * Lớp tương thích — `Panel` thật nằm ở `components/ui/Panel`.
 *
 * Bản này từng là một trong hai cách dựng thẻ nội dung trong repo (cách kia là
 * `fc/primitives.Panel`), với padding, cỡ tiêu đề và đường kẻ khác nhau. Giữ
 * nguyên chữ ký props để mười trang đang dùng nó không phải đổi cùng lúc, còn
 * phần dựng hình thì đã là bản hợp nhất.
 *
 * @deprecated Import `Panel` từ `components/ui` cho code mới.
 */

interface PanelProps {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  /** Không còn tác dụng: độ nổi của thẻ giờ do tầng nền quyết định, không do prop. */
  elevated?: boolean;
}

export function Panel({ title, action, children, className = "", padded = true }: PanelProps) {
  return (
    <UiPanel title={title} actions={action} padded={padded} className={className}>
      {children}
    </UiPanel>
  );
}
