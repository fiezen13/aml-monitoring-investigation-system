import { ArrowRight, X } from "lucide-react";

import { api } from "../../api/client";
import type { ApiAssignmentDetail } from "../../api/client";
import {
  assignmentChannelLabel,
  assignmentOriginLabel,
  assignmentStatusLabel,
  deadlineText,
  formatDateTime,
  priorityLabel,
} from "../../api/format";
import { useApi } from "../../api/useApi";
import { CaseId } from "../copilot/atoms";

/**
 * Bảng bên: chi tiết một hồ sơ và LỊCH SỬ phân công của nó.
 *
 * Lịch sử là phần quan trọng nhất ở đây, và nó không bao giờ bị ghi đè: mỗi lần
 * chuyển giao, đổi hạn hay đổi ưu tiên là một dòng mới. Khi thanh tra hỏi "vì
 * sao hồ sơ này đổi người ba lần", câu trả lời phải đọc được như một câu chuyện
 * chứ không phải một ô dữ liệu bị ghi chồng.
 */

const EVENT_LABEL: Record<string, string> = {
  case_assigned: "Phân công",
  case_state_changed: "Cập nhật",
  alert_raised: "Hồ sơ vào hàng đợi",
};

const FIELD_LABEL: Record<string, string> = {
  due_at: "hạn xử lý",
  priority: "mức ưu tiên",
  instruction: "chỉ dẫn",
  reminder: "nhắc việc",
};

/** Một dòng lịch sử kể bằng lời, có cả giá trị trước và sau. */
function historyLine(h: ApiAssignmentDetail["history"][number]): string {
  const who = h.actor_name ?? "Hệ thống";
  if (h.event === "case_assigned") {
    if (!h.after) return `${who} thu hồi hồ sơ về hàng đợi chung`;
    return h.before
      ? `${who} chuyển hồ sơ từ ${h.before} sang ${h.after}`
      : `${who} giao hồ sơ cho ${h.after}`;
  }
  if (h.event === "case_state_changed" && h.field) {
    const field = FIELD_LABEL[h.field] ?? h.field;
    if (h.field === "due_at" || h.field === "priority") {
      const before = h.field === "due_at" ? formatDateTime(h.before) : priorityLabel(h.before ?? "");
      const after = h.field === "due_at" ? formatDateTime(h.after) : priorityLabel(h.after ?? "");
      return `${who} đổi ${field}: ${before} → ${after}`;
    }
    return `${who} thêm ${field}`;
  }
  return `${who} · ${EVENT_LABEL[h.event] ?? h.event}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-meta font-semibold tracking-[0.04em] text-ink-low">{label}</div>
      <div className="mt-0.5 text-body text-ink-hi">{children}</div>
    </div>
  );
}

export function AssignmentDetail({
  caseId,
  onClose,
  onReassign,
  canReassign,
}: {
  caseId: string;
  onClose: () => void;
  onReassign: (detail: ApiAssignmentDetail) => void;
  canReassign: boolean;
}) {
  const detail = useApi(() => api.assignmentDetail(caseId), [caseId]);
  const d = detail.data;

  return (
    <>
      <div className="fixed inset-0 z-drawer bg-scrim" onClick={onClose} aria-hidden />
      <aside
        role="dialog"
        aria-label={`Chi tiết phân công ${caseId}`}
        className="fixed inset-y-0 right-0 z-drawer flex w-[min(520px,100vw)] flex-col border-l border-line-strong bg-side shadow-modal"
      >
        <header className="flex flex-none items-start justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="group/case min-w-0">
            <div className="text-h3 font-semibold text-ink-hi">Chi tiết phân công</div>
            <div className="mt-0.5">
              <CaseId id={caseId} />
            </div>
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
          {detail.loading && !d && <p className="text-body text-ink-low">Đang tải…</p>}
          {d && (
            <>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3.5">
                <Field label="Rủi ro">
                  <span className="tabular font-semibold">{Math.round(d.row.risk_score)}</span> ·{" "}
                  {priorityLabel(d.row.priority)}
                </Field>
                <Field label="Trạng thái">{assignmentStatusLabel(d.row.status)}</Field>
                <Field label="Người xử lý">{d.row.assignee_name ?? "Chưa phân công"}</Field>
                <Field label="Được giao">
                  {d.row.assigned_at ? formatDateTime(d.row.assigned_at) : "—"}
                </Field>
                {/* NGƯỜI giao và ĐƯỜNG giao trong cùng một ô. Tách ra hai ô
                    cách nhau thì "Nguồn: Trợ lý AI" đọc riêng ra thành "AI giao
                    hồ sơ này" — sai về trách nhiệm nghiệp vụ. */}
                <Field label="Người giao">
                  {d.row.assigned_by_name ? (
                    <>
                      {d.row.assigned_by_name}
                      <div className="text-data text-ink-dim">
                        {assignmentOriginLabel(d.row.source, d.row.assigned_by_id, d.row.assignee_id)}
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </Field>
                <Field label="Hạn xử lý">
                  {d.row.due_at ? (
                    <>
                      {formatDateTime(d.row.due_at)}
                      <div className="text-data text-ink-low">{deadlineText(d.row.due_at)}</div>
                    </>
                  ) : (
                    "Chưa đặt hạn"
                  )}
                </Field>
              </div>

              {d.notes.length > 0 && (
                <section>
                  <h3 className="text-meta font-semibold tracking-[0.04em] text-ink-low">Chỉ dẫn</h3>
                  <ul className="mt-1.5 space-y-2">
                    {d.notes.map((n, i) => (
                      <li key={i} className="rounded-control border border-line bg-elev px-3 py-2">
                        <p className="text-body text-ink-mid">{n.body}</p>
                        <p className="mt-1 text-data text-ink-dim">
                          {n.author_name ?? "Hệ thống"} · {formatDateTime(n.at)}
                        </p>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              <section>
                <h3 className="text-meta font-semibold tracking-[0.04em] text-ink-low">
                  Lịch sử phân công
                </h3>
                <ol className="relative mt-2 space-y-3 border-l border-line pl-4">
                  {d.history.map((h, i) => (
                    <li key={i} className="relative">
                      <span
                        className="absolute -left-[21px] top-1.5 h-1.5 w-1.5 rounded-full bg-line-emphasis"
                        aria-hidden
                      />
                      <div className="text-body text-ink-hi">{historyLine(h)}</div>
                      <div className="mt-0.5 text-data text-ink-dim">
                        {formatDateTime(h.at)}
                        {h.source && ` · ${assignmentChannelLabel(h.source)}`}
                      </div>
                      {h.reason && <div className="mt-0.5 text-data text-ink-low">“{h.reason}”</div>}
                    </li>
                  ))}
                  {d.history.length === 0 && (
                    <li className="text-body text-ink-low">Chưa có thao tác phân công nào.</li>
                  )}
                </ol>
              </section>
            </>
          )}
        </div>

        {d && canReassign && (
          <footer className="flex flex-none justify-end gap-2 border-t border-line px-5 py-3.5">
            <button
              type="button"
              onClick={() => onReassign(d)}
              className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi hover:border-line-emphasis focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
            >
              <ArrowRight size={13} aria-hidden />
              Chuyển giao
            </button>
          </footer>
        )}
      </aside>
    </>
  );
}
