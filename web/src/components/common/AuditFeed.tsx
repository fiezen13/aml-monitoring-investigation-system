import { useMemo, useState } from "react";

import type { ApiAuditEvent } from "../../api/client";
import { actorLabel, auditEventLabel, caseStateLabel, formatDateTime, roleLabel } from "../../api/format";
import { EmptyState } from "./States";

const ACTOR_DOT: Record<string, string> = {
  system: "bg-ink-low",
  agent: "bg-info",
  analyst: "bg-agent",
  investigator: "bg-agent",
  mlro: "bg-warn",
  auditor: "bg-ink-low",
};

/** Vai trò do HỆ THỐNG/tác tử chạy nền — không ngang hàng với quyết định của
 *  con người, nên được làm dịu và có thể ẩn khỏi mốc nghiệp vụ. */
const SYSTEM_ROLES = new Set(["system", "agent"]);

/**
 * Dòng thời gian nhật ký kiểm toán — chỉ đọc (NT4).
 *
 * Không render nút sửa hay xoá nào, và điều đó không phải chuyện của giao
 * diện: bảng audit_log chặn UPDATE/DELETE bằng trigger ở tầng dữ liệu
 * (db/init/002_audit_immutability.sql). Đây chỉ là chỗ nhìn thấy nó.
 *
 * Mặc định hiện ĐỦ mọi sự kiện (audit phải toàn vẹn), nhưng: JSON kỹ thuật gập
 * vào phần mở rộng, sự kiện chạy nền được làm dịu, và có nút "chỉ mốc nghiệp vụ"
 * để chuyên viên đọc nhanh dòng quyết định của con người.
 */
export function AuditFeed({ events }: { events: ApiAuditEvent[] }) {
  const [businessOnly, setBusinessOnly] = useState(false);

  const systemCount = useMemo(
    () => events.filter((e) => SYSTEM_ROLES.has(e.actor_role)).length,
    [events],
  );
  const shown = businessOnly ? events.filter((e) => !SYSTEM_ROLES.has(e.actor_role)) : events;

  if (events.length === 0) {
    return <EmptyState title="Chưa có sự kiện" detail="Nhật ký kiểm toán chưa ghi nhận thao tác nào." />;
  }

  return (
    <div>
      {systemCount > 0 && (
        <div className="mb-3 flex items-center justify-end">
          <button
            type="button"
            onClick={() => setBusinessOnly((v) => !v)}
            className="rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-mid hover:border-line-emphasis hover:text-ink-hi"
          >
            {businessOnly ? `Hiện cả ${systemCount} bước hệ thống` : "Chỉ mốc nghiệp vụ"}
          </button>
        </div>
      )}

      {shown.length === 0 ? (
        <EmptyState title="Chưa có mốc nghiệp vụ" detail="Mọi sự kiện hiện có đều do hệ thống chạy nền." />
      ) : (
        <ol className="relative ml-2 space-y-4 border-l border-line pl-5">
          {shown.map((event) => {
            const isSystem = SYSTEM_ROLES.has(event.actor_role);
            return (
              <li key={event.audit_id} className="relative">
                <span
                  aria-hidden
                  className={`absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel ${
                    ACTOR_DOT[event.actor_role] ?? "bg-ink-low"
                  } ${isSystem ? "opacity-60" : ""}`}
                />
                <div className="flex flex-wrap items-center gap-2">
                  {/* Quyết định của con người in đậm; bước hệ thống làm dịu để
                      không đọc ngang hàng với hành động của chuyên viên. */}
                  <span className={`text-body ${isSystem ? "text-ink-mid" : "font-semibold text-ink-hi"}`}>
                    {auditEventLabel(event.event_type)}
                  </span>
                  {isSystem && (
                    <span className="rounded bg-elev px-1.5 py-0.5 text-micro text-ink-low">hệ thống</span>
                  )}
                  <span className="tabular text-2xs text-ink-low">{formatDateTime(event.occurred_at)}</span>
                </div>
                <div className="mt-0.5 text-2xs text-ink-mid">
                  <span className="font-medium text-ink-hi">{actorLabel(event.actor, event.actor_name)}</span>
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
            );
          })}
        </ol>
      )}
    </div>
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

  // Các payload còn lại là dữ liệu kỹ thuật — gập vào phần mở rộng để không đổ
  // JSON thô vào dòng thời gian mà chuyên viên phải đọc lướt qua.
  return (
    <details className="mt-1">
      <summary className="cursor-pointer list-none text-2xs text-ink-low hover:text-ink-mid">
        Chi tiết kỹ thuật
      </summary>
      <pre className="mt-1 overflow-x-auto rounded-control border border-line bg-elev px-2 py-1 text-2xs text-ink-mid">
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  );
}
