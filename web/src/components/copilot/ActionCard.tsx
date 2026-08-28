import { AlertTriangle, CalendarClock, CheckCircle2, ClipboardList, UserRound } from "lucide-react";

import type { ApiCopilotAction } from "../../api/client";
import { formatDateTime, priorityLabel } from "../../api/format";

/**
 * Thẻ xác nhận cho một đề xuất của trợ lý điều phối.
 *
 * Dựng từ dữ liệu CÓ CẤU TRÚC, không phải từ Markdown trong câu trả lời. Đây là
 * điểm mấu chốt chứ không phải chi tiết trình bày: nút "xác nhận" vẽ bằng chữ
 * trong đoạn văn thì người dùng không phân biệt được đâu là hành động thật, và
 * một mô hình bị dẫn dắt có thể vẽ ra nút trông y hệt.
 *
 * Thẻ chỉ mang `action_id`. Toàn bộ tham số nằm ở máy chủ, nên trình duyệt
 * không sửa được nội dung việc sắp làm — bấm xác nhận là chấp thuận ĐÚNG thứ
 * vừa hiện trên màn hình.
 */

const ACTION_TITLE: Record<ApiCopilotAction["action_type"], string> = {
  ASSIGN_TASK: "Giao việc",
  REASSIGN_TASK: "Chuyển người phụ trách",
  UPDATE_DEADLINE: "Đổi hạn xử lý",
  UPDATE_PRIORITY: "Đổi mức ưu tiên",
  SEND_REMINDER: "Gửi nhắc việc",
  ADD_INSTRUCTION: "Thêm chỉ dẫn",
};

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-3xs uppercase tracking-wider text-ink-low">{label}</span>
      <span className="text-2xs text-ink-hi">{children}</span>
    </div>
  );
}

export function ActionCard({
  action,
  state,
  onConfirm,
  onCancel,
}: {
  action: ApiCopilotAction;
  /** `pending` còn chờ; `done`/`cancelled`/`failed` là kết cục đã chốt. */
  state: { status: "pending" | "busy" | "done" | "cancelled" | "failed"; message?: string };
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const settled = state.status !== "pending" && state.status !== "busy";

  return (
    <div className="rounded-control border border-primary/40 bg-primary/[0.06] p-3">
      <div className="mb-2.5 flex items-center gap-1.5">
        <ClipboardList size={13} className="text-primary" aria-hidden />
        <span className="text-2xs font-semibold uppercase tracking-wider text-primary">
          {ACTION_TITLE[action.action_type]}
        </span>
      </div>

      <div className="space-y-2.5">
        {action.assignee_display_name && (
          <Row label={action.action_type === "REASSIGN_TASK" ? "Chuyển sang" : "Người nhận"}>
            <span className="inline-flex items-center gap-1.5">
              <UserRound size={12} className="text-ink-mid" aria-hidden />
              <span className="font-medium">{action.assignee_display_name}</span>
              <span className="text-ink-low">· Chuyên viên</span>
            </span>
            {action.action_type === "REASSIGN_TASK" && action.current_assignee_name && (
              <span className="block text-ink-low">Đang do {action.current_assignee_name} phụ trách</span>
            )}
          </Row>
        )}

        <Row label={`Hồ sơ (${action.cases.length})`}>
          <ul className="mt-0.5 space-y-1">
            {action.cases.map((c) => (
              <li key={c.case_id} className="flex flex-wrap items-baseline gap-x-2">
                <span className="tabular font-medium text-info">{c.case_id}</span>
                <span className="text-ink-mid">Rủi ro {Math.round(c.risk_score)}</span>
                <span className="text-ink-low">· {priorityLabel(c.priority)}</span>
              </li>
            ))}
          </ul>
        </Row>

        {action.due_at && (
          <Row label="Hạn xử lý">
            <span className="inline-flex items-center gap-1.5">
              <CalendarClock size={12} className="text-ink-mid" aria-hidden />
              {formatDateTime(action.due_at)}
            </span>
          </Row>
        )}

        {action.priority && <Row label="Mức ưu tiên">{priorityLabel(action.priority)}</Row>}

        {action.instruction && <Row label="Chỉ dẫn">{action.instruction}</Row>}

        {action.reason && <Row label="Lý do đề xuất">{action.reason}</Row>}
      </div>

      {settled ? (
        <div
          className={`mt-3 flex items-start gap-1.5 rounded-control border px-2.5 py-2 text-2xs ${
            state.status === "done"
              ? "border-ok/40 bg-ok/10 text-ok"
              : state.status === "failed"
                ? "border-warn/40 bg-warn/10 text-warn"
                : "border-line bg-elev text-ink-mid"
          }`}
        >
          {state.status === "done" ? (
            <CheckCircle2 size={13} aria-hidden />
          ) : state.status === "failed" ? (
            <AlertTriangle size={13} aria-hidden />
          ) : null}
          <span>{state.message}</span>
        </div>
      ) : (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onConfirm}
            disabled={state.status === "busy"}
            className="rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover disabled:opacity-50"
          >
            {state.status === "busy" ? "Đang thực hiện…" : `Xác nhận ${ACTION_TITLE[action.action_type].toLowerCase()}`}
          </button>
          <button
            type="button"
            onClick={onCancel}
            disabled={state.status === "busy"}
            className="rounded-control border border-line px-3 py-1.5 text-2xs font-medium text-ink-mid hover:text-ink-hi disabled:opacity-50"
          >
            Huỷ
          </button>
          <span className="self-center text-3xs text-ink-low">
            Chưa có gì được ghi cho tới khi bạn xác nhận.
          </span>
        </div>
      )}
    </div>
  );
}
