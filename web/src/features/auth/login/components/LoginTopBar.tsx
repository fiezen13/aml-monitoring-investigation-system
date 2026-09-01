import { useEffect, useState } from "react";

import { LoginBrand } from "./LoginBrand";

/**
 * Thanh trên cùng: thương hiệu bên trái, tình trạng hệ thống bên phải.
 *
 * Nằm trong cùng `fc-shell` với nội dung chính nên logo thẳng hàng với tiêu đề
 * hero, và chỉ báo trạng thái thẳng hàng với mép phải thẻ đăng nhập. Bản cũ đặt
 * thanh này bên trong cột trái, khiến nó bị kéo lệch theo cột thay vì làm khung
 * cho cả trang.
 *
 * Đồng hồ lấy giờ máy người dùng chứ không phải giờ máy chủ — nói rõ múi giờ để
 * không ai hiểu nhầm đó là dấu thời gian của hệ thống.
 */
export function LoginTopBar() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const offset = -now.getTimezoneOffset() / 60;
  const tz = `UTC${offset >= 0 ? "+" : ""}${offset}`;

  return (
    <header className="fc-shell-auth flex flex-none items-center justify-between gap-4 pt-6 lg:pt-7">
      <LoginBrand />

      <div className="hidden items-center gap-3 md:flex">
        <span className="flex items-center gap-2 text-2xs text-ink-soft">
          <span className="h-1.5 w-1.5 flex-none rounded-full bg-ok" aria-hidden />
          Tất cả hệ thống đang trực tuyến
        </span>
        <span className="h-3 w-px bg-line-strong" aria-hidden />
        <span className="tabular font-mono text-2xs text-ink-low">
          {now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} {tz}
        </span>
      </div>
    </header>
  );
}
