import { ChevronRight, Lock, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { auditEventLabel, caseStateLabel, formatDateTime, formatRelative, priorityLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { PageShell } from "../components/ui";
import { StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { PageHeader } from "../components/layout/PageHeader";

const stateTone = (state: string): "ok" | "warn" | "muted" | "info" =>
  state === "XuatHoSo" ? "ok" : state === "ChoNguoiPheDuyet" ? "warn" : state === "DongKhongBaoCao" ? "muted" : "info";

const PRIORITY_TONE: Record<string, "risk" | "warn" | "info" | "muted"> = {
  critical: "risk",
  high: "warn",
  medium: "info",
  low: "muted",
};

const roleLabel = (r: string): string =>
  r === "system" ? "hệ thống" : r === "analyst" ? "chuyên viên" : r === "manager" ? "quản lý" : r || "—";

/**
 * Nhật ký kiểm toán THEO VỤ VIỆC — không phải dòng sự kiện phẳng.
 *
 * Mỗi vụ là một thẻ: giai đoạn hiện tại + dòng thời gian các hành động nghiệp vụ
 * đã làm (điều tra, soạn/sửa SAR, gửi duyệt, phê duyệt, xuất hồ sơ). Bỏ lượt xem
 * và sự kiện kỹ thuật (đăng nhập…) vì chúng không phải hành động trên hồ sơ.
 * Chỉ đọc (NT4): bảng chặn sửa/xoá ở tầng dữ liệu.
 */
export function AuditPage() {
  const [search, setSearch] = useState("");
  const audit = useApi(() => api.auditByCase(60), []);
  const cases = audit.data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return cases;
    return cases.filter(
      (c) =>
        c.case_id.toLowerCase().includes(q) ||
        c.subject.toLowerCase().includes(q) ||
        (c.assigned_to ?? "").toLowerCase().includes(q),
    );
  }, [cases, search]);

  return (
    <PageShell>
      <PageHeader
        title="Nhật ký kiểm toán"
        subtitle="Theo TỪNG vụ việc: vụ đang ở giai đoạn nào và đã làm những gì — tái dựng được khi thanh tra hỏi."
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
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Tìm mã vụ việc, tài khoản chủ thể, người phụ trách..."
            className="w-96 font-normal"
          />
        }
        action={<span className="tabular text-2xs text-ink-low">{filtered.length} vụ việc</span>}
      >
        <div className="space-y-2.5 p-4">
          {audit.loading && <LoadingSkeleton rows={6} />}
          {audit.error && <ErrorState detail={audit.error} onRetry={audit.reload} />}
          {!audit.loading &&
            !audit.error &&
            (filtered.length === 0 ? (
              <EmptyState detail="Chưa có vụ việc nào có hành động ghi vào nhật ký." />
            ) : (
              filtered.map((c) => (
                <details key={c.case_id} className="group rounded-control border border-line bg-elev">
                  <summary className="flex cursor-pointer list-none flex-wrap items-center gap-2 px-3.5 py-2.5">
                    <ChevronRight
                      size={13}
                      className="flex-none text-ink-low transition-transform group-open:rotate-90"
                      aria-hidden
                    />
                    <Link
                      to={`/cases/${c.case_id}`}
                      onClick={(e) => e.stopPropagation()}
                      className="tabular font-mono text-2xs text-info hover:underline"
                    >
                      {c.case_id}
                    </Link>
                    <span className="tabular truncate-1 text-2xs text-ink-mid">{c.subject}</span>
                    <StatusBadge tone={stateTone(c.state)} label={caseStateLabel(c.state)} />
                    <StatusBadge tone={PRIORITY_TONE[c.priority] ?? "muted"} label={priorityLabel(c.priority)} />
                    <span className="ml-auto flex-none text-2xs text-ink-low">
                      {c.assigned_to ? `${c.assigned_to} · ` : ""}
                      {c.event_count} hành động · {formatRelative(c.last_at)}
                    </span>
                  </summary>
                  <div className="border-t border-line px-3.5 py-3">
                    <ol className="relative ml-1.5 space-y-2 border-l border-line pl-4">
                      {c.events.map((e, i) => (
                        <li key={i} className="relative">
                          <span
                            className="absolute -left-[21px] top-1 h-1.5 w-1.5 rounded-full bg-primary"
                            aria-hidden
                          />
                          <div className="flex flex-wrap items-baseline gap-x-2 text-2xs">
                            <span className="font-medium text-ink-hi">{auditEventLabel(e.event_type)}</span>
                            <span className="text-ink-low">· {roleLabel(e.actor_role)}</span>
                            <span className="tabular ml-auto text-ink-low">{formatDateTime(e.occurred_at)}</span>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </div>
                </details>
              ))
            ))}
        </div>
      </Panel>
    </PageShell>
  );
}
