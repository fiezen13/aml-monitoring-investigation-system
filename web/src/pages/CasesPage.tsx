import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { PageHeader } from "../components/layout/PageHeader";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState } from "../components/common/States";
import { DataTable, type Column } from "../components/tables/DataTable";
import { CASES, CASE_STATE_LABEL } from "../data/mockCases";
import type { AmlCase, Priority } from "../types";

const PRIORITY_LABEL: Record<Priority, { label: string; tone: "risk" | "warn" | "info" | "muted" }> = {
  critical: { label: "Critical", tone: "risk" },
  high: { label: "High", tone: "warn" },
  medium: { label: "Medium", tone: "info" },
  low: { label: "Low", tone: "muted" },
};

const STATE_TONE = (state: string): "ok" | "warn" | "info" | "muted" =>
  state === "XuatHoSo"
    ? "ok"
    : state === "ChoNguoiPheDuyet"
      ? "warn"
      : state === "DongKhongBaoCao"
        ? "muted"
        : "info";

/** Danh sách vụ việc — hàng đợi theo điểm rủi ro giảm dần (khớp GET /cases). */
export function CasesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("all");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return CASES.filter(
      (c) =>
        (stateFilter === "all" || c.state === stateFilter) &&
        (!q ||
          c.case_id.toLowerCase().includes(q) ||
          c.title.toLowerCase().includes(q) ||
          c.customer.name.toLowerCase().includes(q)),
    ).sort((a, b) => b.risk_score - a.risk_score);
  }, [search, stateFilter]);

  const columns: Column<AmlCase>[] = [
    {
      key: "id",
      header: "Mã vụ việc",
      render: (c) => <span className="tabular font-medium text-info">{c.case_id}</span>,
    },
    { key: "title", header: "Tiêu đề", render: (c) => c.title },
    {
      key: "subject",
      header: "Chủ thể",
      render: (c) => (
        <span className="inline-flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
            {c.customer.initials}
          </span>
          <span>
            {c.customer.name}
            <span className="tabular block text-2xs text-ink-low">
              {c.subject_account_key}
            </span>
          </span>
        </span>
      ),
    },
    { key: "risk", header: "Điểm rủi ro", render: (c) => <RiskBadge score={c.risk_score} /> },
    {
      key: "priority",
      header: "Ưu tiên",
      render: (c) => (
        <StatusBadge tone={PRIORITY_LABEL[c.priority].tone} label={PRIORITY_LABEL[c.priority].label} />
      ),
    },
    {
      key: "state",
      header: "Trạng thái",
      render: (c) => (
        <StatusBadge tone={STATE_TONE(c.state)} label={CASE_STATE_LABEL[c.state] ?? c.state} />
      ),
    },
    {
      key: "assigned",
      header: "Phụ trách",
      render: (c) => <span className="text-ink-mid">{c.assigned_to ?? "—"}</span>,
    },
    {
      key: "alerts",
      header: "Cảnh báo",
      render: (c) => <span className="tabular">{c.alert_count}</span>,
    },
    {
      key: "created",
      header: "Ngày tạo",
      render: (c) => <span className="tabular text-ink-mid">{c.created_at}</span>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      <PageHeader
        title="Danh sách Vụ việc"
        subtitle="Hàng đợi vụ việc xếp theo điểm rủi ro giảm dần — mỗi vụ việc gom cảnh báo theo chủ thể."
        actions={
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            aria-label="Lọc theo trạng thái"
            className="rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs text-ink-hi focus:outline-none"
          >
            <option value="all">Tất cả trạng thái</option>
            {Object.entries(CASE_STATE_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        }
      />
      <Panel
        padded={false}
        title={
          <SearchInput
            value={search}
            onChange={setSearch}
            placeholder="Tìm kiếm mã vụ việc, chủ thể..."
            className="w-80 font-normal"
          />
        }
      >
        {filtered.length === 0 ? (
          <EmptyState detail="Không có vụ việc nào khớp bộ lọc." />
        ) : (
          <DataTable
            columns={columns}
            rows={filtered}
            rowKey={(c) => c.case_id}
            onRowClick={(c) => navigate(`/cases/${c.case_id}`)}
          />
        )}
      </Panel>
    </div>
  );
}
