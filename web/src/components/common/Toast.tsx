import { CheckCircle2, Info, X, XCircle } from "lucide-react";

import { useApp } from "../../context/AppContext";

const TONE = {
  success: { icon: CheckCircle2, cls: "border-ok/40 text-ok" },
  error: { icon: XCircle, cls: "border-risk/40 text-risk" },
  info: { icon: Info, cls: "border-info/40 text-info" },
} as const;

/** Vùng hiển thị toast — góc phải dưới, tự tắt sau vài giây. */
export function ToastRegion() {
  const { toasts, dismissToast } = useApp();
  if (toasts.length === 0) return null;
  return (
    <div className="fixed bottom-4 right-4 z-[90] flex w-80 flex-col gap-2">
      {toasts.map((toast) => {
        const { icon: Icon, cls } = TONE[toast.tone];
        return (
          <div
            key={toast.id}
            role="status"
            className={`flex items-start gap-2.5 rounded-panel border bg-elev p-3 shadow-xl ${cls}`}
          >
            <Icon size={16} className="mt-0.5 shrink-0" aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold text-ink-hi">
                {toast.title}
              </div>
              {toast.detail && (
                <div className="mt-0.5 text-2xs text-ink-mid">{toast.detail}</div>
              )}
            </div>
            <button
              type="button"
              aria-label="Đóng thông báo"
              onClick={() => dismissToast(toast.id)}
              className="shrink-0 text-ink-low hover:text-ink-hi"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
