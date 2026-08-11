import { BarChart3, CheckCircle2, Eye, EyeOff, Lock, Mail, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";

/** Màn hình đăng nhập — bám bố cục screenshot "Đăng nhập - FIN-07". */
export function LoginPage() {
  const { login, pushToast } = useApp();
  const navigate = useNavigate();
  const [email, setEmail] = useState("hung.nq@velrix.vn");
  const [password, setPassword] = useState("demo-password");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const users = useApi(() => api.loginUsers(), []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const user = await login(email.trim(), password);
      pushToast({
        tone: "success",
        title: "Đăng nhập thành công",
        detail: `${user.name} · ${user.roleLabel}`,
      });
      navigate("/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Đăng nhập thất bại");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-app px-6">
      <div className="grid w-full max-w-5xl gap-10 lg:grid-cols-[1.1fr_400px]">
        {/* Khối thương hiệu bên trái */}
        <div className="hidden flex-col justify-center lg:flex">
          <div className="mb-5 flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-panel border border-primary/40 bg-panel text-primary">
              <ShieldCheck size={22} aria-hidden />
            </span>
            <div>
              <div className="text-[19px] font-bold text-primary">FIN-07 AML Console</div>
              <div className="text-2xs font-semibold uppercase tracking-[0.2em] text-ink-low">
                Financial Intelligence Network
              </div>
            </div>
          </div>
          <h1 className="max-w-md text-[22px] font-bold leading-snug text-ink-hi">
            Hệ thống giám sát và phòng chống rửa tiền thế hệ mới.
          </h1>
          <div className="mt-6 max-w-md space-y-3">
            <div className="flex gap-3 rounded-panel border border-line bg-panel p-3.5">
              <ShieldCheck size={18} className="mt-0.5 shrink-0 text-primary" aria-hidden />
              <div>
                <div className="text-[13px] font-semibold text-ink-hi">Bảo mật đa tầng</div>
                <p className="mt-0.5 text-2xs text-ink-mid">
                  Tất cả truy cập được mã hóa và giám sát bởi hệ thống IDS nội bộ.
                </p>
              </div>
            </div>
            <div className="flex gap-3 rounded-panel border border-line bg-panel p-3.5">
              <BarChart3 size={18} className="mt-0.5 shrink-0 text-primary" aria-hidden />
              <div>
                <div className="text-[13px] font-semibold text-ink-hi">AI Copilot Tích hợp</div>
                <p className="mt-0.5 text-2xs text-ink-mid">
                  Hỗ trợ phân tích hành vi bất thường trong thời gian thực.
                </p>
              </div>
            </div>
          </div>
          <div className="mt-6 flex items-center gap-1.5 text-2xs text-ok">
            <CheckCircle2 size={12} aria-hidden />
            Tất cả hệ thống đang trực tuyến
          </div>
          <div className="mt-1 text-2xs text-ink-low">
            © 2026 Velrix Financial Tech. Toàn quyền bảo lưu.
          </div>
        </div>

        {/* Card đăng nhập */}
        <div className="rounded-panel border border-line bg-panel p-6">
          <h2 className="text-[17px] font-bold text-ink-hi">Đăng nhập</h2>
          <p className="mt-1 text-2xs text-ink-mid">
            Sử dụng tài khoản nội bộ do quản trị viên cấp để truy cập hệ thống.
          </p>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div>
              <label htmlFor="email" className="mb-1 block text-2xs font-semibold text-ink-mid">
                Email công vụ
              </label>
              <div className="relative">
                <Mail size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-low" aria-hidden />
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="example@bank-name.com"
                  className="w-full rounded-control border border-line bg-elev py-2 pl-8 pr-3 text-[13px] text-ink-hi placeholder:text-ink-low focus:border-primary/50 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <div className="mb-1 flex items-center justify-between">
                <label htmlFor="password" className="text-2xs font-semibold text-ink-mid">
                  Mật khẩu
                </label>
                <button type="button" className="text-2xs text-primary hover:underline">
                  Quên mật khẩu?
                </button>
              </div>
              <div className="relative">
                <Lock size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-low" aria-hidden />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-control border border-line bg-elev py-2 pl-8 pr-9 text-[13px] text-ink-hi focus:border-primary/50 focus:outline-none"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-low hover:text-ink-hi"
                >
                  {showPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
            </div>
            <label className="flex items-center gap-2 text-2xs text-ink-mid">
              <input type="checkbox" className="accent-[#00B2A9]" />
              Ghi nhớ đăng nhập trên thiết bị này
            </label>
            {error && (
              <p role="alert" className="rounded-control border border-risk/30 bg-risk/10 px-3 py-2 text-2xs text-risk">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="w-full rounded-control bg-primary py-2.5 text-[14px] font-semibold text-app hover:bg-primary-hover"
            >
              Truy cập hệ thống →
            </button>
          </form>

          <div className="mt-4 rounded-control border border-risk/30 bg-risk/5 px-3 py-2.5 text-2xs leading-relaxed text-ink-mid">
            <span className="font-semibold text-risk">Ghi chú bảo mật:</span> Mọi hành động
            đăng nhập và thao tác trên hệ thống đều được lưu nhật ký (audit log) phục vụ
            mục đích kiểm soát.
          </div>

          <div className="mt-4 border-t border-line pt-3">
            <div className="mb-2 text-2xs font-semibold uppercase tracking-wide text-ink-low">
              Tài khoản demo
            </div>
            <div className="grid grid-cols-1 gap-1">
              {(users.data ?? []).map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => {
                    setEmail(user.email);
                    setError(null);
                  }}
                  className="flex items-center justify-between rounded-control px-2 py-1 text-left text-2xs text-ink-mid hover:bg-elev hover:text-ink-hi"
                >
                  <span>{user.name}</span>
                  <span className="text-ink-low">{user.roleLabel}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
