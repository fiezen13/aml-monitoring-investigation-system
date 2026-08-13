import { AlertCircle, ArrowRight, CheckCircle2, LogIn, Mail, ShieldCheck } from "lucide-react";
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

/**
 * Form đăng nhập.
 *
 * Toàn bộ luồng xác thực giữ nguyên như bản cũ: gọi `login()` của AppContext,
 * đẩy toast, rồi điều hướng sang dashboard. Vòng này chỉ thêm trạng thái đang
 * gửi và trạng thái thành công — hai thứ bản cũ thiếu, khiến bấm nút xong màn
 * hình đứng im và người dùng bấm lại lần nữa.
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
      <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-4" noValidate>
        <div>
          <label htmlFor="email" className="mb-1.5 block text-xs font-semibold text-ink-mid">
            Email công vụ
          </label>
          <div className="group relative">
            <Mail
              size={16}
              aria-hidden
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-low transition-colors group-focus-within:text-primary"
            />
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              value={email}
              disabled={busy}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="ten.nguoidung@nganhang.vn"
              className="h-[52px] w-full rounded-[11px] border border-line bg-sunken pl-11 pr-3.5 text-[13.5px] text-ink-hi outline-none transition-[border-color,box-shadow] placeholder:text-ink-dim focus:border-primary-line focus:shadow-[0_0_0_3px_rgba(18,214,197,0.10)] disabled:opacity-60"
            />
          </div>
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

        <label className="flex cursor-pointer items-center gap-2.5 text-xs text-ink-mid">
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

        <button
          type="submit"
          disabled={busy}
          className="group relative flex h-14 w-full items-center justify-center gap-2 overflow-hidden rounded-[12px] bg-gradient-to-r from-primary to-[#0FBFB2] text-[14px] font-semibold text-app transition-[transform,filter,box-shadow] hover:-translate-y-px hover:brightness-110 hover:shadow-[0_8px_24px_rgba(18,214,197,0.22)] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-80 disabled:hover:translate-y-0"
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
              <CheckCircle2 size={17} aria-hidden />
              Đã xác thực
            </>
          )}
          {status === "idle" && (
            <>
              <LogIn size={17} aria-hidden />
              Truy cập hệ thống
              <ArrowRight
                size={16}
                aria-hidden
                className="transition-transform duration-150 group-hover:translate-x-0.5"
              />
            </>
          )}
        </button>
      </form>

      <div className="mt-4 flex items-start gap-2.5 rounded-control border border-info/25 bg-info/[0.07] px-3 py-2.5">
        <ShieldCheck size={15} className="mt-px flex-none text-info-soft" aria-hidden />
        <p className="text-2xs leading-relaxed text-ink-mid">
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
