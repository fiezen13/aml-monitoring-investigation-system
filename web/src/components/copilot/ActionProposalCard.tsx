import { ClipboardList } from "lucide-react";

import type { ApiCopilotAction } from "../../api/client";
import { formatDateTime, priorityLabel } from "../../api/format";
import { CaseId, FieldLabel, Initials, PriorityBadge, RiskScore } from "./atoms";

/**
 * Thẻ ĐỀ XUẤT — trạng thái chờ người duyệt bấm.
 *
 * Đây là thứ duy nhất trong khung trò chuyện được phép nổi hơn chữ thường, vì
 * nó là chỗ người dùng ra quyết định. Nhưng "nổi" ở đây là một đường viền và
 * một nền rất nhạt, không phải một khối teal: cả thẻ tô màu nhấn thì không còn
 * gì để nhấn nút chính.
 *
 * Thứ tự đọc cố ý: LÀM GÌ (tiêu đề) → CHO AI (người nhận + tải hiện có) → TRÊN
 * HỒ SƠ NÀO (bảng) → RÀNG BUỘC (hạn, chỉ dẫn) → NÚT. Người duyệt cần biết mình
 * đang chất việc lên ai trước khi đọc danh sách hồ sơ.
 */

const ACTION_TITLE: Record<ApiCopilotAction["action_type"], string> = {
  ASSIGN_TASK: "Đề xuất giao việc",
  REASSIGN_TASK: "Đề xuất chuyển người phụ trách",
  UPDATE_DEADLINE: "Đề xuất đổi hạn xử lý",
  UPDATE_PRIORITY: "Đề xuất đổi mức ưu tiên",
  SEND_REMINDER: "Đề xuất gửi nhắc việc",
  ADD_INSTRUCTION: "Đề xuất thêm chỉ dẫn",
};

/** Nhãn nút chính. Nói rõ việc sắp xảy ra, không phải "Xác nhận" chung chung. */
function ctaLabel(action: ApiCopilotAction): string {
  const n = action.cases.length;
  switch (action.action_type) {
    case "ASSIGN_TASK":
      return `Giao ${n} hồ sơ`;
    case "REASSIGN_TASK":
      return `Chuyển ${n} hồ sơ`;
    case "UPDATE_DEADLINE":
      return `Đặt hạn cho ${n} hồ sơ`;
    case "UPDATE_PRIORITY":
      return `Đổi ưu tiên ${n} hồ sơ`;
    case "SEND_REMINDER":
      return `Gửi nhắc ${n} hồ sơ`;
    default:
      return `Ghi chỉ dẫn cho ${n} hồ sơ`;
  }
}

export function AssigneeRow({ action }: { action: ApiCopilotAction }) {
  const name = action.assignee_display_name;
  if (!name) return null;
  const load = action.assignee_workload;
  // Chỉ nói con số đo được. Không có dữ liệu tải việc thì im lặng — đoán bừa
  // "đang rảnh" là cách nhanh nhất để giao nhầm người.
  const meta = [
    "Chuyên viên AML",
    load ? `${load.open_cases} hồ sơ đang xử lý` : null,
    load && load.overdue_cases > 0 ? `${load.overdue_cases} quá hạn` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex items-center gap-2.5">
      <Initials name={name} />
      <div className="min-w-0">
        <div className="truncate text-body-lg font-medium text-ink-hi">{name}</div>
        <div className="truncate text-data text-ink-low">{meta}</div>
        {action.action_type === "REASSIGN_TASK" && action.current_assignee_name && (
          <div className="truncate text-data text-ink-dim">
            Đang do {action.current_assignee_name} phụ trách
          </div>
        )}
      </div>
    </div>
  );
}

/** Bảng hồ sơ: mã · điểm · mức ưu tiên, ba cột thẳng hàng để quét bằng mắt. */
export function CaseList({ cases }: { cases: ApiCopilotAction["cases"] }) {
  return (
    <ul className="divide-y divide-line-faint">
      {cases.map((c) => (
        <li
          key={c.case_id}
          className="group/case grid grid-cols-[1fr_auto_auto] items-center gap-x-3 py-1"
        >
          <CaseId id={c.case_id} />
          <RiskScore score={c.risk_score} />
          <PriorityBadge priority={c.priority} />
        </li>
      ))}
    </ul>
  );
}

export function ActionProposalCard({
  action,
  busy,
  onConfirm,
  onEdit,
  onCancel,
}: {
  action: ApiCopilotAction;
  busy: boolean;
  onConfirm: () => void;
  onEdit: () => void;
  onCancel: () => void;
}) {
  return (
    <section
      aria-label={ACTION_TITLE[action.action_type]}
      className="rounded-panel border border-accent-line bg-accent-softer"
    >
      <header className="flex items-center gap-2 border-b border-line-faint px-5 py-2.5">
        <ClipboardList size={14} className="flex-none text-primary" aria-hidden />
        <h3 className="text-body-lg font-semibold text-ink-hi">{ACTION_TITLE[action.action_type]}</h3>
        <span className="ml-auto whitespace-nowrap text-data text-ink-low">
          {action.cases.length} hồ sơ
        </span>
      </header>

      <div className="space-y-3.5 px-5 py-3.5">
        <AssigneeRow action={action} />

        <div>
          <FieldLabel>Hồ sơ</FieldLabel>
          <div className="mt-1">
            <CaseList cases={action.cases} />
          </div>
        </div>

        {(action.due_at || action.priority) && (
          <div className="grid grid-cols-2 gap-4">
            {action.due_at && (
              <div>
                <FieldLabel>Hạn xử lý</FieldLabel>
                <div className="tabular mt-1 text-body text-ink-hi">{formatDateTime(action.due_at)}</div>
              </div>
            )}
            {action.priority && (
              <div>
                <FieldLabel>Mức ưu tiên</FieldLabel>
                <div className="mt-1 text-body text-ink-hi">{priorityLabel(action.priority)}</div>
              </div>
            )}
          </div>
        )}

        {action.instruction && (
          <div>
            <FieldLabel>Chỉ dẫn</FieldLabel>
            <p className="mt-1 text-body leading-relaxed text-ink-mid">{action.instruction}</p>
          </div>
        )}
      </div>

      <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line-faint px-5 py-2.5">
        <span className="mr-auto text-data text-ink-dim">Chưa có gì được ghi cho tới khi bạn xác nhận.</span>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="rounded-control px-3 py-1.5 text-body font-medium text-ink-mid transition-colors hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis disabled:opacity-50"
        >
          Huỷ
        </button>
        <button
          type="button"
          onClick={onEdit}
          disabled={busy}
          className="rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi transition-colors hover:border-line-emphasis focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis disabled:opacity-50"
        >
          Chỉnh sửa
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="rounded-control bg-primary px-3.5 py-1.5 text-body font-semibold text-app transition-colors hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:opacity-50"
        >
          {busy ? "Đang thực hiện…" : ctaLabel(action)}
        </button>
      </footer>
    </section>
  );
}
