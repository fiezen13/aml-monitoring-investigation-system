import { Lock } from "lucide-react";
import { useMemo, useState } from "react";

import { AuditTimeline } from "../components/common/AuditTimeline";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState } from "../components/common/States";
import { AUDIT_ACTION_LABEL, AUDIT_EVENTS } from "../data/mockAudit";

/** Audit trail — chỉ đọc (NT4): không có nút sửa hay xóa ở bất kỳ đâu. */
export function AuditPage() {
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("all");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return AUDIT_EVENTS.filter(
      (e) =>
        (actionFilter === "all" || e.action === actionFilter) &&
        (!q ||
          e.actor.toLowerCase().includes(q) ||
          e.target.toLowerCase().includes(q) ||
          e.detail.toLowerCase().includes(q)),
    );
  }, [search, actionFilter]);

  return (
    <div className="mx-auto max-w-[980px]">
      <PageHeader
        title="Audit trail"
        subtitle="Nhật ký bất biến của mọi hành động trong hệ thống — vụ việc phải tái dựng được khi thanh tra hỏi."
        actions={
          <span className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-mid">
            <Lock size={12} aria-hidden />
            Chỉ đọc — ghi thêm, không sửa xóa
          </span>
        }
      />
      <Panel
        padded={false}
        title={
          <div className="flex items-center gap-3">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Tìm theo người thực hiện, mã đối tượng..."
              className="w-80 font-normal"
            />
            <select
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
              aria-label="Lọc theo hành động"
              className="rounded-control border border-line bg-elev px-2 py-1.5 text-2xs text-ink-hi focus:outline-none"
            >
              <option value="all">Tất cả hành động</option>
              {Object.entries(AUDIT_ACTION_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        }
        action={
          <span className="tabular text-2xs text-ink-low">{filtered.length} sự kiện</span>
        }
      >
        <div className="p-4">
          {filtered.length === 0 ? (
            <EmptyState detail="Không có sự kiện audit nào khớp bộ lọc." />
          ) : (
            <AuditTimeline events={filtered} />
          )}
        </div>
      </Panel>
    </div>
  );
}
