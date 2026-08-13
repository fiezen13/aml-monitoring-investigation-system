import { Fingerprint, LayoutGrid, Lock, ShieldAlert } from "lucide-react";
import { useNavigate } from "react-router-dom";

/** Màn hình 403 — bám screenshot "Truy cập bị từ chối - FIN-07". */
export function AccessDenied() {
  const navigate = useNavigate();
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-app px-6 text-center">
      <div className="relative">
        <span className="flex h-20 w-20 items-center justify-center rounded-panel border border-line bg-panel text-primary">
          <Lock size={30} aria-hidden />
        </span>
        <span className="tabular absolute -right-2 -top-2 rounded-full bg-risk px-1.5 py-0.5 text-2xs font-bold text-white">
          403
        </span>
      </div>
      <h1 className="mt-6 text-[18px] font-bold uppercase tracking-[0.15em] text-ink-hi">
        Truy cập bị từ chối
      </h1>
      <p className="mt-2 max-w-sm text-[13px] leading-relaxed text-ink-mid">
        Hành động của bạn đã bị ngăn chặn. Hệ thống giám sát Velrix xác nhận bạn không có
        đủ thẩm quyền để truy cập vào phân đoạn dữ liệu nhạy cảm này.
      </p>
      <div className="mt-6 grid grid-cols-2 gap-3">
        <div className="flex items-center gap-2.5 rounded-panel border border-line bg-panel px-4 py-3 text-left">
          <Fingerprint size={16} className="shrink-0 text-ink-mid" aria-hidden />
          <div>
            <div className="text-2xs text-ink-low">Mã yêu cầu</div>
            <div className="tabular text-2xs font-semibold text-primary">
              REQ-403-B592-VLRX
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2.5 rounded-panel border border-line bg-panel px-4 py-3 text-left">
          <ShieldAlert size={16} className="shrink-0 text-ink-mid" aria-hidden />
          <div>
            <div className="text-2xs text-ink-low">Cấp độ bảo mật</div>
            <div className="text-2xs font-semibold text-warn">Hạn chế (L3)</div>
          </div>
        </div>
      </div>
      <div className="mt-6 flex gap-3">
        <button
          type="button"
          onClick={() => navigate("/dashboard")}
          className="inline-flex items-center gap-1.5 rounded-control bg-primary px-4 py-2 text-[13px] font-semibold text-app hover:bg-primary-hover"
        >
          <LayoutGrid size={14} aria-hidden />
          Quay lại Dashboard
        </button>
        <button
          type="button"
          className="rounded-control border border-line px-4 py-2 text-[13px] font-medium text-ink-hi hover:border-line-emphasis"
        >
          Liên hệ Quản trị viên
        </button>
      </div>
      <div className="mt-10 text-2xs uppercase tracking-[0.2em] text-ink-low">
        <Lock size={10} className="mr-1 inline" aria-hidden />
        FIN-07 AML Protocol Active
      </div>
      <div className="tabular mt-1 text-2xs text-ink-low">
        Thời gian hệ thống: 2026-05-19 14:32:01 UTC
      </div>
    </div>
  );
}
