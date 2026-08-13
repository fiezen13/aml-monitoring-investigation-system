import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";

import type { SarStatus, SarValidationIssue } from "../../types";

interface ValidationPanelProps {
  status: SarStatus;
  issues: SarValidationIssue[];
  onFix?: () => void;
}

/** Trạng thái Validation của bản nháp SAR — khớp panel phải screenshot SAR-2026-007. */
export function ValidationPanel({ status, issues, onFix }: ValidationPanelProps) {
  const failed = issues.some((i) => i.severity === "error");
  const ranAndPassed =
    status === "VALIDATION_PASSED" ||
    status === "PENDING_REVIEW" ||
    status === "APPROVED";

  return (
    <section
      className={`rounded-panel border bg-panel ${
        failed && status !== "DRAFT" ? "border-risk/50" : "border-line"
      }`}
    >
      <header className="flex items-center justify-between border-b border-line px-4 py-3">
        <div>
          <div className="text-[13px] font-semibold text-ink-hi">Trạng thái kiểm chứng</div>
          <div className="mt-0.5 text-2xs text-ink-mid">
            {status === "DRAFT" && "Trạng thái: Chưa chạy kiểm chứng"}
            {status === "VALIDATION_FAILED" &&
              `Trạng thái: Cần rà soát lại (${issues.length} lỗi)`}
            {ranAndPassed && "Trạng thái: Kiểm chứng đạt"}
            {status === "REJECTED" && "Trạng thái: Bị từ chối"}
            {status === "NEEDS_INFO" && "Trạng thái: Cần bổ sung thông tin"}
          </div>
        </div>
        {ranAndPassed ? (
          <CheckCircle2 size={16} className="text-ok" aria-hidden />
        ) : (
          <AlertTriangle size={16} className="text-warn" aria-hidden />
        )}
      </header>
      <div className="space-y-2 p-4">
        {ranAndPassed && issues.length === 0 && (
          <div className="flex items-center gap-2 rounded-control border border-ok/30 bg-ok/10 px-3 py-2 text-[13px] text-ok">
            <CheckCircle2 size={14} aria-hidden />
            Toàn bộ nhận định đều có bằng chứng, số liệu khớp công cụ tính toán.
          </div>
        )}
        {issues.map((issue) => (
          <div
            key={issue.id}
            className={`rounded-control border px-3 py-2 ${
              issue.severity === "error"
                ? "border-risk/30 bg-risk/5"
                : "border-warn/30 bg-warn/5"
            }`}
          >
            <div
              className={`flex items-center gap-1.5 text-[13px] font-semibold ${
                issue.severity === "error" ? "text-risk" : "text-warn"
              }`}
            >
              {issue.severity === "error" ? (
                <XCircle size={13} aria-hidden />
              ) : (
                <AlertTriangle size={13} aria-hidden />
              )}
              {issue.title}
            </div>
            <p className="mt-0.5 text-2xs text-ink-mid">{issue.detail}</p>
          </div>
        ))}
        {failed && onFix && (
          <button
            type="button"
            onClick={onFix}
            className="w-full rounded-control bg-primary py-2 text-md font-semibold text-app transition-colors hover:bg-primary-hover"
          >
            Đồng bộ số liệu từ công cụ tính toán & bổ sung chứng từ
          </button>
        )}
      </div>
    </section>
  );
}
