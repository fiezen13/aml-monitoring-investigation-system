import { X } from "lucide-react";
import { useState } from "react";

import { api } from "../../api/client";
import type { ApiAssignmentRow, ApiWorkloadPerson } from "../../api/client";
import { CaseId } from "../copilot/atoms";

/**
 * Chuyển giao một hồ sơ sang chuyên viên khác.
 *
 * LÝ DO là bắt buộc, không phải để làm khó người dùng: chuyển giao là thao tác
 * duy nhất ở đây lấy việc khỏi tay một người, và sáu tháng sau câu hỏi "vì sao
 * hồ sơ này đổi người ba lần" phải có câu trả lời trong nhật ký.
 *
 * Máy chủ nhận kèm người xử lý mà màn hình ĐANG hiển thị; lệch với thực tế thì
 * nó báo xung đột thay vì ghi đè.
 */
export function ReassignDrawer({
  row,
  candidates,
  onClose,
  onDone,
}: {
  row: ApiAssignmentRow;
  candidates: ApiWorkloadPerson[];
  onClose: () => void;
  onDone: () => void;
}) {
  const [assignee, setAssignee] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const others = candidates.filter((c) => c.employee_id !== row.assignee_id);

  async function submit() {
    if (!assignee || reason.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      await api.reassignCase(row.case_id, {
        assignee_id: assignee,
        reason: reason.trim(),
        expected_assignee: row.assignee_id,
      });
      onDone();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không chuyển giao được, thử lại sau.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-drawer bg-scrim" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-label="Chuyển giao hồ sơ"
        className="fixed inset-y-0 right-0 z-drawer flex w-[min(520px,100vw)] flex-col border-l border-line-strong bg-side shadow-modal"
      >
        <header className="flex flex-none items-center justify-between border-b border-line px-5 py-3.5">
          <h2 className="text-h3 font-semibold text-ink-hi">Chuyển giao hồ sơ</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="rounded-control p-1.5 text-ink-mid hover:bg-elev hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
          >
            <X size={15} aria-hidden />
          </button>
        </header>

        <div className="copilot-scroll min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
          <div className="group/case">
            <div className="text-meta font-semibold tracking-[0.04em] text-ink-low">Hồ sơ</div>
            <div className="mt-0.5">
              <CaseId id={row.case_id} />
            </div>
          </div>

          <div>
            <div className="text-meta font-semibold tracking-[0.04em] text-ink-low">
              Hiện đang xử lý bởi
            </div>
            <div className="mt-0.5 text-body text-ink-hi">{row.assignee_name ?? "Chưa phân công"}</div>
          </div>

          <div>
            <div className="text-meta font-semibold tracking-[0.04em] text-ink-low">Chuyển cho</div>
            <div className="mt-1.5 space-y-1.5">
              {others.map((c) => (
                <button
                  key={c.employee_id}
                  type="button"
                  onClick={() => setAssignee(c.employee_id)}
                  aria-pressed={assignee === c.employee_id}
                  className={`flex w-full items-center justify-between gap-3 rounded-control border px-3 py-2 text-left transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis ${
                    assignee === c.employee_id
                      ? "border-accent-line bg-accent-soft"
                      : "border-line hover:border-line-emphasis"
                  }`}
                >
                  <span className="text-body font-medium text-ink-hi">{c.name}</span>
                  <span className="whitespace-nowrap text-data text-ink-low">
                    {c.open_cases} đang xử lý
                    {c.overdue > 0 && <span className="text-warn"> · {c.overdue} quá hạn</span>}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="reason" className="text-meta font-semibold tracking-[0.04em] text-ink-low">
              Lý do chuyển giao
            </label>
            <textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="Ví dụ: điều chỉnh tải công việc."
              className="mt-1.5 w-full resize-none rounded-control border border-line bg-elev px-3 py-2 text-body text-ink-hi placeholder:text-ink-dim focus:border-line-emphasis focus:outline-none"
            />
            <p className="mt-1 text-data text-ink-dim">Lý do được ghi vào lịch sử phân công.</p>
          </div>

          {error && (
            <p role="alert" className="rounded-control border border-warn/40 bg-warn/10 px-3 py-2 text-body text-warn">
              {error}
            </p>
          )}
        </div>

        <footer className="flex flex-none justify-end gap-2 border-t border-line px-5 py-3.5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-control px-3 py-1.5 text-body font-medium text-ink-mid hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
          >
            Huỷ
          </button>
          <button
            type="button"
            onClick={() => void submit()}
            disabled={busy || !assignee || reason.trim().length < 3}
            className="rounded-control bg-primary px-3.5 py-1.5 text-body font-semibold text-app hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50"
          >
            {busy ? "Đang chuyển…" : "Xác nhận chuyển giao"}
          </button>
        </footer>
      </aside>
    </>
  );
}
