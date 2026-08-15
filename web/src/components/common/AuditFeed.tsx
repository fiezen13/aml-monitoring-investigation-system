import type { ApiAuditEvent } from "../../api/client";
import { auditEventLabel, caseStateLabel, formatDateTime, roleLabel } from "../../api/format";
import { EmptyState } from "./States";

const ACTOR_DOT: Record<string, string> = {
  system: "bg-info",
  agent: "bg-info",
  analyst: "bg-info",
  investigator: "bg-agent",
  mlro: "bg-warn",
  auditor: "bg-ink-low",
};

/**
 * Dòng thời gian nhật ký kiểm toán — chỉ đọc (NT4).
 *
 * Không render nút sửa hay xoá nào, và điều đó không phải chuyện của giao
 * diện: bảng audit_log chặn UPDATE/DELETE bằng trigger ở tầng dữ liệu
 * (db/init/002_audit_immutability.sql). Đây chỉ là chỗ nhìn thấy nó.
 */
export function AuditFeed({ events }: { events: ApiAuditEvent[] }) {
  if (events.length === 0) {
    return <EmptyState title="Chưa có sự kiện" detail="Nhật ký kiểm toán chưa ghi nhận thao tác nào." />;
  }

  return (
    <ol className="relative ml-2 space-y-4 border-l border-line pl-5">
      {events.map((event) => (
        <li key={event.audit_id} className="relative">
          <span
            aria-hidden
            className={`absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel ${
              ACTOR_DOT[event.actor_role] ?? "bg-ink-low"
            }`}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-body font-semibold text-ink-hi">{auditEventLabel(event.event_type)}</span>
            <span className="tabular text-2xs text-ink-low">{formatDateTime(event.occurred_at)}</span>
          </div>
          <div className="mt-0.5 text-2xs text-ink-mid">
            <span className="font-medium text-ink-hi">{event.actor}</span>
            {" · "}
            {roleLabel(event.actor_role)}
            {event.case_id && (
              <>
                {" → "}
                <span className="tabular text-info">{event.case_id}</span>
              </>
            )}
          </div>
          <PayloadLine payload={event.payload} />
        </li>
      ))}
    </ol>
  );
}

function PayloadLine({ payload }: { payload: Record<string, unknown> }) {
  const keys = Object.keys(payload);
  if (keys.length === 0) return null;

  // Chuyển trạng thái là loại sự kiện đọc nhiều nhất, nên nó được viết ra
  // thành câu thay vì đổ JSON thô như các loại còn lại.
  if (typeof payload.from === "string" && typeof payload.to === "string") {
    return (
      <div className="mt-1 inline-flex items-center gap-1.5 rounded-control border border-line bg-elev px-2 py-1 text-2xs">
        <span className="text-ink-mid">{caseStateLabel(payload.from)}</span>
        <span className="text-ink-low" aria-hidden>
          →
        </span>
        <span className="font-semibold text-ink-hi">{caseStateLabel(payload.to)}</span>
      </div>
    );
  }

  return (
    <pre className="mt-1 overflow-x-auto rounded-control border border-line bg-elev px-2 py-1 text-2xs text-ink-mid">
      {JSON.stringify(payload)}
    </pre>
  );
}
