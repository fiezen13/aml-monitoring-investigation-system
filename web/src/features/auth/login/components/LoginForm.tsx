import { AlertCircle, CheckCircle2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../../../../api/client";
import { useApi } from "../../../../api/useApi";
import { useApp } from "../../../../context/AppContext";
import type { User } from "../../../../types";
import { DemoAccountList } from "./DemoAccountList";
import { LoginTrustIndicators } from "./LoginTrustIndicators";
import { PasswordField } from "./PasswordField";

type Status = "idle" | "submitting" | "success";

/** Ô nhập dùng chung cho email và mật khẩu — cao 44px, viền mảnh, focus rõ. */
const FIELD =
  "h-11 w-full rounded-control border border-line-strong bg-sunken px-3 text-md text-ink-hi outline-none transition-[border-color,box-shadow] placeholder:text-ink-dim hover:border-line-emphasis focus:border-primary/60 focus:shadow-[0_0_0_3px_rgba(32,199,167,0.14)] disabled:opacity-60";

/**
 * Form đăng nhập.
 *
 * Toàn bộ luồng xác thực giữ nguyên: gọi `login()` của AppContext, đẩy toast,
 * rồi điều hướng sang dashboard. Vòng refactor này chỉ đụng tới lớp thị giác.
 */
export function LoginForm() {
  const { login, pushToast } = useApp();
  const navigate = useNavigate();
  const users = useApi(() => api.loginUsers(), []);

  const [email, setEmail] = useState("hung.nq@velrix.vn");
  const [password, setPassword] = useState("demo-password");
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<Status>("idle");

  const busy = status !== "idle";

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setStatus("submitting");
    try {
      const user = await login(email.trim(), password);
      setStatus("success");
      pushToast({
        tone: "success",
        title: "Đăng nhập thành công",
        detail: `${user.name} · ${user.roleLabel}`,
      });
      // Đủ để thấy nút đổi trạng thái, không đủ để thành thời gian chờ.
      window.setTimeout(() => navigate("/dashboard"), 260);
    } catch (cause) {
      setStatus("idle");
      setError(cause instanceof Error ? cause.message : "Đăng nhập thất bại");
    }
  };

  const pickDemo = (user: User) => {
    setEmail(user.email);
    setError(null);
  };

  return (
    <>
      <form onSubmit={handleSubmit} className="mt-6 flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-2xs font-medium text-ink-mid">
            Email công vụ
          </label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="username"
            value={email}
            disabled={busy}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="ten.nguoidung@nganhang.vn"
            className={FIELD}
          />
        </div>

        <PasswordField
          value={password}
          onChange={setPassword}
          disabled={busy}
          onForgot={() =>
            pushToast({
              tone: "info",
              title: "Đặt lại mật khẩu",
              detail: "Liên hệ quản trị viên hệ thống để được cấp lại mật khẩu.",
            })
          }
        />

        <label className="flex cursor-pointer items-center gap-2.5 text-2xs text-ink-mid">
          <input
            type="checkbox"
            checked={remember}
            onChange={(e) => setRemember(e.target.checked)}
            className="h-4 w-4 accent-primary"
          />
          Ghi nhớ đăng nhập trên thiết bị này
        </label>

        {/* Vùng lỗi phải được đọc lên ngay khi xuất hiện, và không được đẩy bố
            cục — nên nó luôn chiếm chỗ sẵn trong luồng, chỉ đổi nội dung. */}
        <div aria-live="polite" aria-atomic="true">
          {error && (
            <p
              role="alert"
              className="animate-up flex items-start gap-2 rounded-control border border-risk/35 bg-risk/10 px-3 py-2.5 text-2xs leading-relaxed text-risk-soft"
            >
              <AlertCircle size={14} className="mt-px flex-none" aria-hidden />
              {error}
            </p>
          )}
        </div>

        {/* Teal đặc, chữ tối, không gradient và không quầng sáng ngoài. Đây là
            chỗ duy nhất trên màn hình được tô teal đầy — nhờ vậy nó là hành
            động rõ ràng chứ không phải một khối màu nữa trong nhiều khối. */}
        <button
          type="submit"
          disabled={busy}
          className="mt-1 flex h-11 w-full items-center justify-center gap-2 rounded-control bg-primary text-md font-semibold text-[#04140F] transition-colors hover:bg-primary-hover active:bg-[#1BAF92] disabled:cursor-not-allowed disabled:opacity-70"
        >
          {status === "submitting" && (
            <>
              <span
                className="h-4 w-4 animate-spin rounded-full border-2 border-app/30 border-t-app"
                aria-hidden
              />
              Đang xác thực…
            </>
          )}
          {status === "success" && (
            <>
              <CheckCircle2 size={16} aria-hidden />
              Đã xác thực
            </>
          )}
          {status === "idle" && "Truy cập hệ thống"}
        </button>
      </form>

      <div className="fc-auth-tight mt-4 flex items-start gap-2.5 rounded-control bg-info/[0.06] px-3 py-2.5">
        <ShieldCheck size={14} className="mt-px flex-none text-info-soft" aria-hidden />
        <p className="text-2xs leading-relaxed text-ink-low">
          Mọi hành động đăng nhập và thao tác trên hệ thống đều được lưu nhật ký (audit log) phục vụ mục đích kiểm
          soát.
        </p>
      </div>

      <DemoAccountList
        users={users.data ?? []}
        loading={users.loading}
        selectedEmail={email}
        onPick={pickDemo}
      />

      <LoginTrustIndicators />
    </>
  );
}
