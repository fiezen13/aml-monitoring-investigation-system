import { LoginForm } from "./LoginForm";

/**
 * Thẻ đăng nhập.
 *
 * Đây phải là thứ rõ nhất trên màn hình, nhưng cách làm rõ không phải là phát
 * sáng: nền đặc hơn nền trang, viền sáng hơn một bậc, bóng đổ sâu và mềm. Bản
 * cũ dùng bo góc 22px, quầng teal ở mép trên và bóng 70px — dáng của một thẻ
 * marketing, không phải của phần mềm ngân hàng.
 */
export function LoginPanel() {
  return (
    <div className="flex w-full max-w-[440px] flex-col">
      <div
        className="fc-auth-card animate-up w-full rounded-[12px] border border-line-strong bg-panel px-[30px] py-7 shadow-[0_24px_60px_-28px_rgba(0,0,0,0.9)]"
        style={{ animationDelay: "120ms", animationFillMode: "backwards" }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-ink-hi">Đăng nhập</h1>
          <span className="fc-eyebrow">Truy cập nội bộ</span>
        </div>
        <p className="mt-1.5 text-2xs leading-relaxed text-ink-low">
          Sử dụng tài khoản do quản trị viên hệ thống cấp.
        </p>

        <LoginForm />
      </div>
    </div>
  );
}
