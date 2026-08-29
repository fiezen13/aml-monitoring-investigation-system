import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { ApiAssignmentRow, ApiWorkloadPerson } from "../../api/client";
import { priorityLabel } from "../../api/format";
import { CaseId, PriorityBadge } from "../copilot/atoms";

/**
 * Ngăn kéo giao việc thủ công.
 *
 * Hai quyết định đáng nói:
 *
 * 1. Ô chọn người nhận hiện KHỐI LƯỢNG VIỆC ngay bên cạnh tên. Chọn người mà
 *    không thấy họ đang gánh gì thì việc phân bổ chỉ là bốc thăm, và người
 *    đang quá tải lại tiếp tục nhận thêm.
 * 2. Hồ sơ ĐÃ CÓ người xử lý được đánh dấu rõ. Giao đè lên là chuyển giao —
 *    một việc khác hẳn về ý nghĩa, nên phải nhìn thấy trước khi bấm.
 */

export function AssignDrawer({
  open,
  onClose,
  onDone,
  preselected,
  candidates,
}: {
  open: boolean;
  onClose: () => void;
  onDone: (assigned: number) => void;
  /** Hồ sơ đã chọn sẵn từ bảng (giao hàng loạt). */
  preselected: ApiAssignmentRow[];
  candidates: ApiWorkloadPerson[];
}) {
  const [assignee, setAssignee] = useState("");
  const [priority, setPriority] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [dueTime, setDueTime] = useState("16:00");
  const [instruction, setInstruction] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmBulk, setConfirmBulk] = useState(false);

  useEffect(() => {
    if (open) {
      setError(null);
      setConfirmBulk(false);
    }
  }, [open]);

  const sorted = useMemo(
    () => [...candidates].sort((a, b) => a.open_cases - b.open_cases),
    [candidates],
  );
  const picked = sorted.find((c) => c.employee_id === assignee);
  const alreadyHeld = preselected.filter((c) => c.assignee_id);
  // Lô lớn phải xác nhận thêm một nhịp: một cú bấm nhầm không được đổi chủ hai
  // chục hồ sơ.
  const needsExtraConfirm = preselected.length >= 10;

  async function submit() {
    if (!assignee || preselected.length === 0) return;
    if (needsExtraConfirm && !confirmBulk) {
      setConfirmBulk(true);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const due = dueDate ? new Date(`${dueDate}T${dueTime || "00:00"}`).toISOString() : undefined;
      const res = await api.assignCases({
        case_ids: preselected.map((c) => c.case_id),
        assignee_id: assignee,
        priority: priority || undefined,
        due_at: due,
        instruction: instruction.trim() || undefined,
        reason: "Quản lý giao việc trên màn Phân công",
      });
      if (res.conflicts.length > 0) {
        setError(
          `${res.assigned.length} hồ sơ đã giao. ${res.conflicts.length} hồ sơ không giao được: ` +
            res.conflicts.map((c) => c.message).join("; "),
        );
      }
      onDone(res.assigned.length);
      if (res.conflicts.length === 0) onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Không giao được, thử lại sau.");
    } finally {
      setBusy(false);
      setConfirmBulk(false);
    }
  }

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-drawer bg-scrim" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-label="Giao việc"
        className="fixed inset-y-0 right-0 z-drawer flex w-[min(560px,100vw)] flex-col border-l border-line-strong bg-side shadow-modal"
      >
        <header className="flex flex-none items-center justify-between border-b border-line px-5 py-3.5">
          <div>
            <h2 className="text-h3 font-semibold text-ink-hi">Giao việc</h2>
            <p className="mt-0.5 text-data text-ink-low">
              {preselected.length} hồ sơ được chọn
              {alreadyHeld.length > 0 && ` · ${alreadyHeld.length} hồ sơ đang có người xử lý`}
            </p>
          </div>
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
          <section>
            <h3 className="text-meta font-semibold tracking-[0.04em] text-ink-low">Hồ sơ</h3>
            <ul className="mt-1.5 divide-y divide-line-faint rounded-panel border border-line">
              {preselected.map((c) => (
                <li key={c.case_id} className="group/case flex items-center gap-3 px-3 py-1.5">
                  <span className="flex-1 truncate">
                    <CaseId id={c.case_id} />
                  </span>
                  <span className="tabular text-body font-semibold text-ink-hi">
                    {Math.round(c.risk_score)}
                  </span>
                  <PriorityBadge priority={c.priority} />
                  {c.assignee_name && (
                    <span className="whitespace-nowrap text-data text-warn">
                      Đang: {c.assignee_name}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <label htmlFor="assignee" className="text-meta font-semibold tracking-[0.04em] text-ink-low">
              Người xử lý
            </label>
            <div className="mt-1.5 space-y-1.5">
              {sorted.map((c) => (
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
          </section>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label htmlFor="priority" className="text-meta font-semibold tracking-[0.04em] text-ink-low">
                Mức ưu tiên
              </label>
              <select
                id="priority"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
                className="mt-1.5 w-full rounded-control border border-line bg-elev px-2.5 py-1.5 text-body text-ink-hi focus:border-line-emphasis focus:outline-none"
              >
                <option value="">Giữ nguyên</option>
                {["critical", "high", "medium", "low"].map((p) => (
                  <option key={p} value={p}>
                    {priorityLabel(p)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="due" className="text-meta font-semibold tracking-[0.04em] text-ink-low">
                Hạn xử lý
              </label>
              <div className="mt-1.5 flex gap-1.5">
                <input
                  id="due"
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  className="min-w-0 flex-1 rounded-control border border-line bg-elev px-2.5 py-1.5 text-body text-ink-hi focus:border-line-emphasis focus:outline-none"
                />
                <input
                  type="time"
                  aria-label="Giờ"
                  value={dueTime}
                  onChange={(e) => setDueTime(e.target.value)}
                  className="w-[92px] rounded-control border border-line bg-elev px-2 py-1.5 text-body text-ink-hi focus:border-line-emphasis focus:outline-none"
                />
              </div>
            </div>
          </div>

          <div>
            <label htmlFor="instruction" className="text-meta font-semibold tracking-[0.04em] text-ink-low">
              Chỉ dẫn
            </label>
            <textarea
              id="instruction"
              value={instruction}
              onChange={(e) => setInstruction(e.target.value)}
              rows={3}
              placeholder="Ví dụ: rà soát hồ sơ và bổ sung bằng chứng còn thiếu."
              className="mt-1.5 w-full resize-none rounded-control border border-line bg-elev px-3 py-2 text-body text-ink-hi placeholder:text-ink-dim focus:border-line-emphasis focus:outline-none"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-control border border-warn/40 bg-warn/10 px-3 py-2 text-body text-warn">
              {error}
            </p>
          )}

          {confirmBulk && picked && (
            <div role="alert" className="rounded-panel border border-warn/40 bg-warn/[0.07] px-3.5 py-3">
              <p className="text-body text-ink-hi">
                Bạn sắp giao <strong>{preselected.length} hồ sơ</strong> cho {picked.name}.
              </p>
              <p className="mt-1 text-data text-ink-mid">
                Người này hiện đang có {picked.open_cases} hồ sơ đang xử lý
                {picked.overdue > 0 && `, trong đó ${picked.overdue} hồ sơ quá hạn`}.
              </p>
            </div>
          )}
        </div>

        <footer className="flex flex-none items-center justify-end gap-2 border-t border-line px-5 py-3.5">
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
            disabled={busy || !assignee || preselected.length === 0}
            className="rounded-control bg-primary px-3.5 py-1.5 text-body font-semibold text-app hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50"
          >
            {busy
              ? "Đang giao…"
              : confirmBulk
                ? `Xác nhận giao ${preselected.length} hồ sơ`
                : `Giao ${preselected.length} hồ sơ`}
          </button>
        </footer>
      </aside>
    </>
  );
}
