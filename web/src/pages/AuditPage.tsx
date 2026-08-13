import { Lock, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import { auditEventLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { AuditFeed } from "../components/common/AuditFeed";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { PageHeader } from "../components/layout/PageHeader";

/** Danh mục loại sự kiện — đúng ràng buộc CHECK của audit_log.event_type. */
const EVENT_TYPES = [
  "agent_query",
  "alert_raised",
  "case_state_changed",
  "submitted_for_approval",
  "approved",
  "rejected",
  "more_info_requested",
  "file_exported",
  "case_viewed",
  "user_login",
  "setting_changed",
  "user_changed",
  "sar_updated",
  "validation_run",
];

/** Nhật ký kiểm toán — chỉ đọc (NT4). Bảng chặn UPDATE/DELETE bằng trigger ở tầng
 *  dữ liệu, nên ở đây không có nút sửa hay xoá nào để mà bỏ sót. */
export function AuditPage() {
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("");

  const audit = useApi(
    () => api.audit({ event_type: eventType || undefined, limit: 300 }),
    [eventType],
  );

  const events = audit.data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return events;
    return events.filter(
      (e) =>
        e.actor.toLowerCase().includes(q) ||
        e.actor_role.toLowerCase().includes(q) ||
        (e.case_id ?? "").toLowerCase().includes(q) ||
        auditEventLabel(e.event_type).toLowerCase().includes(q) ||
        JSON.stringify(e.payload).toLowerCase().includes(q),
    );
  }, [events, search]);

  return (
    <div className="mx-auto max-w-[980px]">
      <PageHeader
        title="Nhật ký kiểm toán"
        subtitle="Nhật ký bất biến của mọi hành động trong hệ thống — vụ việc phải tái dựng được khi thanh tra hỏi."
        actions={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-mid">
              <Lock size={12} aria-hidden />
              Chỉ đọc — ghi thêm, không sửa xoá
            </span>
            <button
              type="button"
              onClick={audit.reload}
              className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
            >
              <RefreshCw size={12} aria-hidden />
              Làm mới
            </button>
          </div>
        }
      />
      <Panel
        padded={false}
        title={
          <div className="flex flex-wrap items-center gap-3">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Tìm theo người thực hiện, mã vụ việc..."
              className="w-80 font-normal"
            />
            <select
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
              aria-label="Lọc theo loại sự kiện"
              className="rounded-control border border-line bg-elev px-2 py-1.5 text-2xs text-ink-hi focus:outline-none"
            >
              <option value="">Tất cả loại sự kiện</option>
              {EVENT_TYPES.map((value) => (
                <option key={value} value={value}>
                  {auditEventLabel(value)}
                </option>
              ))}
            </select>
          </div>
        }
        action={<span className="tabular text-2xs text-ink-low">{filtered.length} sự kiện</span>}
      >
        <div className="p-4">
          {audit.loading && <LoadingSkeleton rows={6} />}
          {audit.error && <ErrorState detail={audit.error} onRetry={audit.reload} />}
          {!audit.loading &&
            !audit.error &&
            (filtered.length === 0 ? (
              <EmptyState detail="Không có sự kiện nào khớp bộ lọc." />
            ) : (
              <AuditFeed events={filtered} />
            ))}
        </div>
      </Panel>
    </div>
  );
}
