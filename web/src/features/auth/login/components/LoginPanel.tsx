import { ShieldCheck } from "lucide-react";

import { LoginForm } from "./LoginForm";

/**
 * Thẻ đăng nhập.
 *
 * Đây phải là thứ rõ nhất trên màn hình: nền đặc hơn nền trang, viền sáng hơn,
 * bóng đổ sâu. Quả cầu phía sau chỉ là bối cảnh — nếu nó hút mắt hơn thẻ này
 * thì cả trang đã hỏng mục đích.
 */
export function LoginPanel() {
  return (
    <div className="flex w-full flex-col items-center justify-center gap-5 px-5 py-7 [@media(max-height:830px)]:py-4 lg:w-[clamp(400px,38vw,540px)] lg:px-8 xl:px-10">
      {/* Cột trái ẩn dưới lg, nên trên màn hẹp phải có nhận diện ở đây — nếu
          không người dùng nhìn thấy một cái thẻ đăng nhập không tên. */}
      <div className="flex items-center gap-2.5 lg:hidden">
        <span className="flex h-9 w-9 items-center justify-center rounded-control border border-primary-line bg-panel text-primary">
          <ShieldCheck size={18} aria-hidden />
        </span>
        <div>
          <div className="text-base font-bold tracking-tight text-ink-hi">
            FIN-07 <span className="text-primary">AML Console</span>
          </div>
          <div className="text-3xs font-semibold uppercase tracking-[0.18em] text-ink-low">
            Financial Intelligence Network
          </div>
        </div>
      </div>

      <div
        className="animate-up relative w-full max-w-[480px] rounded-[22px] border border-line-strong bg-panel/92 p-6 shadow-[0_28px_70px_-24px_rgba(0,0,0,0.85)] backdrop-blur-md [@media(max-height:830px)]:p-5 xl:p-7"
        style={{ animationDelay: "120ms", animationFillMode: "backwards" }}
      >
        {/* Vệt sáng mảnh ở mép trên — mẹo cũ để một mặt phẳng tối trông có khối. */}
        <span
          aria-hidden
          className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-primary/45 to-transparent"
        />

        <div className="flex items-start gap-3">
          <span className="relative flex h-11 w-11 flex-none items-center justify-center rounded-[13px] border border-primary-line bg-primary-soft text-primary">
            <ShieldCheck size={22} aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight text-ink-hi">Đăng nhập</h1>
              <span className="rounded-chip border border-primary-line bg-primary-soft px-2 py-0.5 font-mono text-3xs uppercase tracking-[0.1em] text-primary">
                Secure
              </span>
            </div>
            <p className="mt-1 text-2xs leading-relaxed text-ink-low">
              Sử dụng tài khoản nội bộ do quản trị viên cấp để truy cập hệ thống.
            </p>
          </div>
        </div>

        <LoginForm />
      </div>
    </div>
  );
}
