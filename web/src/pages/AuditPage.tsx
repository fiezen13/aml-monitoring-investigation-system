import { Check, ChevronRight, Lock, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";

import type { ApiAuditCaseEvent, ApiAuditMilestone } from "../api/client";
import { api } from "../api/client";
import { caseStateLabel, caseStepLabel, formatDateTime, formatRelative, priorityLabel } from "../api/format";
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
  r === "system" ? "hệ thống" : r === "agent" ? "tác tử AI" : r === "analyst" ? "chuyên viên" : r === "manager" ? "quản lý" : r || "—";

const DECISION_LABELS: Record<string, string> = {
  APPROVE: "Phê duyệt",
  REJECT: "Từ chối",
  REQUEST_MORE_INFORMATION: "Yêu cầu bổ sung thông tin",
};

const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v.trim() : null);

/**
 * Diễn giải một sự kiện audit thành CÂU NGHIỆP VỤ: đã làm gì + ghi chú/lý do.
 * Lấy chi tiết từ payload (from→to, lý do gửi duyệt, quyết định rà soát…) để
 * nhật ký đọc được như một câu chuyện, không phải mã sự kiện thô.
 */
function describeEvent(e: ApiAuditCaseEvent): { title: string; note: string | null } {
  const p = e.payload ?? {};
  switch (e.event_type) {
    case "investigation_started":
      return { title: "Khởi tạo điều tra", note: str(p.alert_id) ? `từ cảnh báo ${str(p.alert_id)}` : null };
    case "investigation_completed":
      return { title: "Tác tử điều tra hoàn tất", note: "đã dựng bằng chứng và điểm rủi ro" };
    case "investigation_failed":
      return { title: "Phiên điều tra gặp lỗi", note: str(p.error) ?? str(p.reason) };
    case "investigation_reviewed": {
      const d = str(p.decision);
      const decision = d ? DECISION_LABELS[d] ?? d : "Đã rà soát";
      const reason = str(p.reason);
      return { title: `Rà soát điều tra — ${decision}`, note: reason ? `“${reason}”` : null };
    }
    case "case_state_changed": {
      const from = str(p.from);
      const to = str(p.to);
      return {
        title: "Chuyển giai đoạn",
        note: from && to ? `${caseStepLabel(from)} → ${caseStepLabel(to)}` : to ? `→ ${caseStepLabel(to)}` : null,
      };
    }
    case "sar_updated": {
      const a = str(p.action);
      const map: Record<string, string> = { edited: "sửa nội dung", created: "tạo bản nháp", regenerated: "soạn lại bằng AI" };
      return { title: "Cập nhật hồ sơ SAR", note: a ? map[a] ?? a : null };
    }
    case "validation_run": {
      const uncited = typeof p.uncited === "number" ? p.uncited : null;
      return {
        title: "Kiểm tra trích dẫn bằng chứng",
        note: uncited === null ? null : uncited === 0 ? "mọi luận điểm đều có dẫn chứng" : `${uncited} luận điểm chưa có dẫn chứng`,
      };
    }
    case "submitted_for_approval":
      return { title: "Trình quản lý phê duyệt", note: str(p.reason) ? `“${str(p.reason)}”` : null };
    case "file_exported":
      return { title: "Xuất hồ sơ (PDF)", note: str(p.kind) };
    default:
      return { title: e.event_type.replace(/_/g, " "), note: null };
  }
}

/** Thanh cột mốc: vụ đã đi qua giai đoạn nào, đang dừng ở đâu. */
function MilestoneTrack({ milestones }: { milestones: ApiAuditMilestone[] }) {
  return (
    <div className="flex flex-wrap items-start gap-x-1 gap-y-3">
      {milestones.map((m, i) => (
        <div key={m.key} className="flex items-start">
          <div className="flex w-[92px] flex-col items-center gap-1 text-center">
            <span
              className={
                "grid h-5 w-5 place-items-center rounded-full border text-[9px] " +
                (m.status === "done"
                  ? "border-primary bg-primary text-white"
                  : m.status === "current"
                    ? "border-warn bg-warn/15 text-warn ring-2 ring-warn/30"
                    : "border-line bg-elev text-ink-low")
              }
              aria-hidden
            >
              {m.status === "done" ? <Check size={11} strokeWidth={3} /> : i + 1}
            </span>
            <span
              className={
                "text-[10px] leading-tight " +
                (m.status === "pending" ? "text-ink-low" : "font-medium text-ink-hi")
              }
            >
              {m.label}
            </span>
            <span className="tabular text-[9px] text-ink-low">
              {m.reached_at ? formatRelative(m.reached_at) : m.status === "current" ? "đang xử lý" : "—"}
            </span>
          </div>
          {i < milestones.length - 1 && (
            <span
              className={"mt-2.5 h-px w-3 flex-none " + (milestones[i + 1].status === "pending" ? "bg-line" : "bg-primary/50")}
              aria-hidden
            />
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * Nhật ký kiểm toán THEO VỤ VIỆC — không phải dòng sự kiện phẳng.
 *
 * Mỗi vụ mở ra: (1) thanh cột mốc cho biết vụ đã qua giai đoạn nào và đang dừng
 * ở đâu; (2) dòng thời gian chi tiết — ai làm gì, lúc nào, kèm ghi chú/lý do.
 * Tự chứa: đọc trọn vòng đời hồ sơ ngay tại đây, không rời trang. Chỉ đọc (NT4).
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
        (c.assigned_name ?? c.assigned_to ?? "").toLowerCase().includes(q),
    );
  }, [cases, search]);

  return (
    <PageShell>
      <PageHeader
        title="Nhật ký kiểm toán"
        subtitle="Theo TỪNG vụ việc: đã qua những giai đoạn nào, ai làm gì, ghi chú ra sao — tái dựng được khi thanh tra hỏi."
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
                    <span className="tabular font-mono text-2xs text-ink-hi">{c.case_id}</span>
                    <span className="tabular truncate-1 text-2xs text-ink-mid">{c.subject}</span>
                    <StatusBadge tone={stateTone(c.state)} label={caseStateLabel(c.state)} />
                    <StatusBadge tone={PRIORITY_TONE[c.priority] ?? "muted"} label={priorityLabel(c.priority)} />
                    <span className="ml-auto flex-none text-2xs text-ink-low">
                      {c.assigned_name ? `${c.assigned_name} · ` : ""}
                      {c.event_count} hành động · {formatRelative(c.last_at)}
                    </span>
                  </summary>
                  <div className="space-y-3.5 border-t border-line px-3.5 py-3.5">
                    {/* Cột mốc: vụ đang ở giai đoạn nào */}
                    <div>
                      <div className="mb-2.5 text-2xs font-medium uppercase tracking-wide text-ink-low">Giai đoạn hồ sơ</div>
                      <div className="overflow-x-auto pb-1">
                        <MilestoneTrack milestones={c.milestones} />
                      </div>
                    </div>
                    {/* Dòng thời gian chi tiết: đã làm gì, ai, lúc nào */}
                    <div>
                      <div className="mb-2 text-2xs font-medium uppercase tracking-wide text-ink-low">Diễn biến ({c.event_count})</div>
                      <ol className="relative ml-1.5 space-y-2.5 border-l border-line pl-4">
                        {c.events.map((e, i) => {
                          const d = describeEvent(e);
                          return (
                            <li key={i} className="relative">
                              <span
                                className="absolute -left-[21px] top-1 h-1.5 w-1.5 rounded-full bg-primary"
                                aria-hidden
                              />
                              <div className="flex flex-wrap items-baseline gap-x-2 text-2xs">
                                <span className="font-medium text-ink-hi">{d.title}</span>
                                <span className="tabular ml-auto flex-none text-ink-low">{formatDateTime(e.occurred_at)}</span>
                              </div>
                              {d.note && <div className="mt-0.5 text-2xs text-ink-mid">{d.note}</div>}
                              <div className="mt-0.5 text-[10px] text-ink-low">
                                {e.actor_name} · {roleLabel(e.actor_role)}
                              </div>
                            </li>
                          );
                        })}
                      </ol>
                    </div>
                  </div>
                </details>
              ))
            ))}
        </div>
      </Panel>
    </PageShell>
  );
}
