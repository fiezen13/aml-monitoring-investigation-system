import { Clock, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";

/**
 * Hàng trên cùng: thương hiệu bên trái, tình trạng hệ thống bên phải.
 *
 * Đồng hồ lấy giờ máy người dùng chứ không phải giờ máy chủ — nói rõ múi giờ
 * để không ai hiểu nhầm đó là dấu thời gian của hệ thống.
 */
export function LoginBrand() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(id);
  }, []);

  const offset = -now.getTimezoneOffset() / 60;
  const tz = `UTC${offset >= 0 ? "+" : ""}${offset}`;

  return (
    <header className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="relative flex h-11 w-11 items-center justify-center rounded-[13px] border border-primary-line bg-panel text-primary">
          <span className="absolute inset-0 rounded-[13px] bg-primary/10 blur-[10px]" aria-hidden />
          <ShieldCheck size={22} className="relative" aria-hidden />
        </span>
        <div>
          <div className="text-xl font-bold tracking-tight text-ink-hi">
            FIN-07 <span className="text-primary">Bảng điều khiển AML</span>
          </div>
          <div className="mt-0.5 text-3xs font-semibold uppercase tracking-[0.22em] text-ink-low">
            Mạng lưới tình báo tài chính
          </div>
        </div>
      </div>

      <div className="hidden items-center gap-3 md:flex">
        <span className="flex items-center gap-2 text-2xs text-ok">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-pulse rounded-full bg-ok" aria-hidden />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
          </span>
          Tất cả hệ thống đang trực tuyến
        </span>
        <span className="h-3 w-px bg-line-strong" aria-hidden />
        <span className="flex items-center gap-1.5 font-mono text-2xs text-ink-low">
          <Clock size={12} aria-hidden />
          {now.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" })} ({tz})
        </span>
      </div>
    </header>
  );
}
