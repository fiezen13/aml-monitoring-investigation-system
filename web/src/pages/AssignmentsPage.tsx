import { Sparkles, UserPlus } from "lucide-react";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { ApiAssignmentDetail, ApiAssignmentRow } from "../api/client";
import {
  assignmentSourceLabel,
  assignmentStatusLabel,
  deadlineText,
  formatDateTime,
} from "../api/format";
import { useApi } from "../api/useApi";
import { AssignDrawer } from "../components/assignments/AssignDrawer";
import { AssignmentDetail } from "../components/assignments/AssignmentDetail";
import { ReassignDrawer } from "../components/assignments/ReassignDrawer";
import { CaseId, PriorityBadge } from "../components/copilot/atoms";
import { Column, DataTable, PageShell, Panel } from "../components/ui";

/**
 * Phân công & tải công việc — nguồn sự thật duy nhất cho việc "hồ sơ ở đâu".
 *
 * Trợ lý AI giúp giao việc NHANH; trang này giúp KIỂM SOÁT. Cả hai ghi qua cùng
 * một dịch vụ và đọc cùng một bảng, nên một lượt giao qua trò chuyện hiện ở đây
 * ngay — không có "dữ liệu của chatbot" tách riêng.
 *
 * Là màn hình VẬN HÀNH: bảng dày, lọc mạnh, ít biểu đồ. Quản lý cần thấy nhiều
 * hồ sơ trong một khung nhìn chứ không cần một trang bìa đẹp.
 */

/** Bộ lọc dựng sẵn — cùng một bảng, khác điều kiện. */
const QUICK_VIEWS = [
  { key: "", label: "Tất cả" },
  { key: "unassigned", label: "Chưa phân công" },
  { key: "overdue", label: "Quá hạn" },
  { key: "due_soon", label: "Sắp đến hạn" },
] as const;

const STATUS_TONE: Record<string, string> = {
  unassigned: "text-ink-mid",
  in_progress: "text-ink-hi",
  needs_info: "text-info",
  due_soon: "text-warn",
  overdue: "text-risk",
  completed: "text-ink-dim",
};

export function AssignmentsPage() {
  const [status, setStatus] = useState("");
  const [assignee, setAssignee] = useState("");
  const [source, setSource] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Record<string, ApiAssignmentRow>>({});
  const [assignOpen, setAssignOpen] = useState(false);
  const [detailFor, setDetailFor] = useState<string | null>(null);
  const [reassigning, setReassigning] = useState<ApiAssignmentRow | null>(null);

  const overview = useApi(() => api.assignmentOverview(), []);
  const list = useApi(
    () =>
      api.assignments({
        status: status || undefined,
        assignee: assignee || undefined,
        source: source || undefined,
        q: q || undefined,
        page,
        page_size: 25,
      }),
    [status, assignee, source, q, page],
  );

  const team = overview.data?.workload ?? [];
  const canAssign = overview.data?.can_assign ?? false;
  const seesTeam = overview.data?.sees_team ?? false;
  const chosen = useMemo(() => Object.values(selected), [selected]);

  function refresh() {
    list.reload();
    overview.reload();
    setSelected({});
  }

  function applyFilter(next: string) {
    setStatus(next);
    setPage(1);
  }

  const columns: Column<ApiAssignmentRow>[] = [
    {
      key: "case",
      header: "Hồ sơ",
      render: (r) => (
        <span className="group/case flex items-center gap-2">
          {canAssign && (
            <input
              type="checkbox"
              aria-label={`Chọn hồ sơ ${r.case_id}`}
              checked={Boolean(selected[r.case_id])}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) =>
                setSelected((s) => {
                  const next = { ...s };
                  if (e.target.checked) next[r.case_id] = r;
                  else delete next[r.case_id];
                  return next;
                })
              }
              className="accent-primary"
            />
          )}
          <CaseId id={r.case_id} />
        </span>
      ),
    },
    {
      key: "risk",
      header: "Rủi ro",
      numeric: true,
      sortValue: (r) => r.risk_score,
      render: (r) => <span className="tabular font-semibold text-ink-hi">{Math.round(r.risk_score)}</span>,
    },
    { key: "priority", header: "Ưu tiên", render: (r) => <PriorityBadge priority={r.priority} /> },
    {
      key: "assignee",
      header: "Người xử lý",
      render: (r) =>
        r.assignee_name ? (
          <span className="text-ink-hi">{r.assignee_name}</span>
        ) : (
          <span className="text-ink-dim">Chưa phân công</span>
        ),
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (r) => (
        <span className={STATUS_TONE[r.status] ?? "text-ink-mid"}>{assignmentStatusLabel(r.status)}</span>
      ),
    },
    {
      key: "due",
      header: "Hạn xử lý",
      sortValue: (r) => r.due_at ?? "",
      render: (r) =>
        r.due_at ? (
          <span className="block">
            <span className="tabular text-ink-hi">{formatDateTime(r.due_at)}</span>
            <span
              className={`block text-meta ${
                r.status === "overdue" ? "text-risk" : r.status === "due_soon" ? "text-warn" : "text-ink-dim"
              }`}
            >
              {deadlineText(r.due_at)}
            </span>
          </span>
        ) : (
          <span className="text-ink-dim">Chưa đặt hạn</span>
        ),
    },
    {
      key: "source",
      header: "Nguồn phân công",
      render: (r) => (
        <span
          className="text-ink-mid"
          title={
            r.source === "ai_copilot" && r.assigned_by_name
              ? `Được đề xuất qua Trợ lý AI và xác nhận bởi ${r.assigned_by_name}.`
              : r.assigned_by_name
                ? `Giao bởi ${r.assigned_by_name}.`
                : undefined
          }
        >
          {assignmentSourceLabel(r.source)}
        </span>
      ),
    },
  ];

  return (
    <PageShell
      title="Phân công & tải công việc"
      subtitle="Theo dõi, phân bổ và điều phối hồ sơ AML trong nhóm."
      actions={
        canAssign ? (
          <button
            type="button"
            onClick={() => setAssignOpen(true)}
            disabled={chosen.length === 0}
            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover disabled:opacity-40"
          >
            <UserPlus size={13} aria-hidden />
            {chosen.length > 0 ? `Giao ${chosen.length} hồ sơ` : "Giao việc"}
          </button>
        ) : undefined
      }
    >
      <div className="space-y-3">
        {/* Số liệu vận hành. Bấm được để lọc — con số và bảng phải nói cùng
            một chuyện, nên cách nhanh nhất là cho chúng nối thẳng vào nhau. */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
          {[
            { key: "unassigned", label: "Chưa phân công", value: overview.data?.unassigned },
            { key: "in_progress", label: "Đang xử lý", value: overview.data?.in_progress },
            { key: "due_soon", label: "Sắp đến hạn", value: overview.data?.due_soon, tone: "text-warn" },
            { key: "overdue", label: "Quá hạn", value: overview.data?.overdue, tone: "text-risk" },
            { key: "", label: "Ưu tiên cao", value: overview.data?.high_priority },
          ].map((k) => (
            <button
              key={k.label}
              type="button"
              onClick={() => applyFilter(k.key)}
              aria-pressed={status === k.key && k.key !== ""}
              className={`rounded-panel border px-3.5 py-2.5 text-left transition-colors ${
                status === k.key && k.key !== ""
                  ? "border-accent-line bg-accent-soft"
                  : "border-line bg-panel hover:border-line-emphasis"
              }`}
            >
              <div className="text-meta uppercase tracking-wider text-ink-low">{k.label}</div>
              <div className={`tabular mt-0.5 text-h2 font-bold ${k.tone ?? "text-ink-hi"}`}>
                {k.value ?? "—"}
              </div>
            </button>
          ))}
        </div>

        {seesTeam && team.length > 0 && (
          <Panel title="Tải công việc của nhóm" padded={false}>
            <ul className="divide-y divide-line-faint">
              {team.map((p) => (
                <li key={p.employee_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setAssignee(assignee === p.employee_id ? "" : p.employee_id);
                      setPage(1);
                    }}
                    aria-pressed={assignee === p.employee_id}
                    className={`flex w-full items-center gap-4 px-4 py-2 text-left transition-colors ${
                      assignee === p.employee_id ? "bg-accent-soft" : "hover:bg-elev"
                    }`}
                  >
                    <span className="w-44 flex-none truncate text-body font-medium text-ink-hi">
                      {p.name}
                    </span>
                    <span className="tabular w-24 flex-none text-data text-ink-mid">
                      {p.open_cases} hồ sơ
                    </span>
                    <span className="tabular w-20 flex-none text-data text-ink-mid">
                      {p.high_priority} cao
                    </span>
                    <span
                      className={`tabular w-24 flex-none text-data ${p.overdue > 0 ? "text-risk" : "text-ink-dim"}`}
                    >
                      {p.overdue} quá hạn
                    </span>
                    <span
                      className={`tabular w-28 flex-none text-data ${p.due_soon > 0 ? "text-warn" : "text-ink-dim"}`}
                    >
                      {p.due_soon} sắp đến hạn
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel
          title="Danh sách phân công"
          padded={false}
          actions={
            <div className="flex flex-wrap items-center gap-1.5">
              {QUICK_VIEWS.map((v) => (
                <button
                  key={v.label}
                  type="button"
                  onClick={() => applyFilter(v.key)}
                  aria-pressed={status === v.key}
                  className={`rounded-full border px-2.5 py-1 text-data transition-colors ${
                    status === v.key
                      ? "border-accent-line bg-accent-soft text-ink-hi"
                      : "border-line text-ink-mid hover:text-ink-hi"
                  }`}
                >
                  {v.label}
                </button>
              ))}
              <select
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setPage(1);
                }}
                aria-label="Nguồn phân công"
                className="rounded-control border border-line bg-elev px-2 py-1 text-data text-ink-mid"
              >
                <option value="">Mọi nguồn</option>
                <option value="manual">Thủ công</option>
                <option value="ai_copilot">Trợ lý AI</option>
              </select>
              <input
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder="Tìm mã hồ sơ…"
                aria-label="Tìm mã hồ sơ"
                className="w-40 rounded-control border border-line bg-elev px-2.5 py-1 text-data text-ink-hi placeholder:text-ink-dim"
              />
              {(status || assignee || source || q) && (
                <button
                  type="button"
                  onClick={() => {
                    setStatus("");
                    setAssignee("");
                    setSource("");
                    setQ("");
                    setPage(1);
                  }}
                  className="text-data text-info-soft hover:text-info"
                >
                  Xoá bộ lọc
                </button>
              )}
            </div>
          }
        >
          <DataTable
            columns={columns}
            rows={list.data?.rows ?? []}
            rowKey={(r) => r.case_id}
            onRowClick={(r) => setDetailFor(r.case_id)}
            loading={list.loading && !list.data}
            dense
            minWidth={880}
            emptyTitle={status === "unassigned" ? "Không có hồ sơ chưa phân công" : "Không tìm thấy hồ sơ"}
            emptyDetail={
              status === "unassigned"
                ? "Tất cả hồ sơ hiện đã có người xử lý."
                : "Không có hồ sơ nào phù hợp với bộ lọc hiện tại."
            }
            footer={
              list.data && list.data.total > list.data.page_size ? (
                <div className="flex items-center justify-between px-4 py-2 text-data text-ink-mid">
                  <span>
                    {(list.data.page - 1) * list.data.page_size + 1}–
                    {Math.min(list.data.page * list.data.page_size, list.data.total)} trên{" "}
                    {list.data.total.toLocaleString("vi-VN")} hồ sơ
                  </span>
                  <span className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className="rounded-control border border-line px-2 py-0.5 disabled:opacity-40"
                    >
                      Trước
                    </button>
                    <button
                      type="button"
                      onClick={() => setPage((p) => p + 1)}
                      disabled={page * list.data.page_size >= list.data.total}
                      className="rounded-control border border-line px-2 py-0.5 disabled:opacity-40"
                    >
                      Sau
                    </button>
                  </span>
                </div>
              ) : undefined
            }
          />
        </Panel>

        <p className="flex items-center gap-1.5 px-1 text-data text-ink-dim">
          <Sparkles size={12} aria-hidden />
          Hồ sơ giao qua Trợ lý AI hiện ở đây ngay, với nguồn phân công là “Trợ lý AI”.
        </p>
      </div>

      {assignOpen && (
        <AssignDrawer
          open={assignOpen}
          onClose={() => setAssignOpen(false)}
          onDone={() => refresh()}
          preselected={chosen}
          candidates={team}
        />
      )}
      {detailFor && (
        <AssignmentDetail
          caseId={detailFor}
          canReassign={canAssign}
          onClose={() => setDetailFor(null)}
          onReassign={(d: ApiAssignmentDetail) => {
            setDetailFor(null);
            setReassigning(d.row);
          }}
        />
      )}
      {reassigning && (
        <ReassignDrawer
          row={reassigning}
          candidates={team}
          onClose={() => setReassigning(null)}
          onDone={refresh}
        />
      )}
    </PageShell>
  );
}
