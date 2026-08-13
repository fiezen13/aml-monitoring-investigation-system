import { RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { caseStateLabel, formatDateTime, priorityLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { PageHeader } from "../components/layout/PageHeader";
import { DataTable, type Column } from "../components/tables/DataTable";
import type { ApiCase } from "../api/client";

const PRIORITY_TONE: Record<string, "risk" | "warn" | "info" | "muted"> = {
  critical: "risk",
  high: "warn",
  medium: "info",
  low: "muted",
};

/** Danh sách 12 trạng thái — đúng ràng buộc CHECK của aml_case.state. */
const CASE_STATES = [
  "TiepNhanCanhBao",
  "TruyHoiBangChung",
  "PhanTichDoThi",
  "DoiChieuTrungPhatPEP",
  "TinhToanBangCongCu",
  "LapLuanGanTypology",
  "SoanHoSoNghiVan",
  "KiemChungBangChung",
  "ChoNguoiPheDuyet",
  "DieuTraBoSung",
  "XuatHoSo",
  "DongKhongBaoCao",
];

const stateTone = (state: string): "ok" | "warn" | "info" | "muted" =>
  state === "XuatHoSo" ? "ok" : state === "ChoNguoiPheDuyet" ? "warn" : state === "DongKhongBaoCao" ? "muted" : "info";

/** Hàng đợi vụ việc theo điểm rủi ro giảm dần (GET /api/v1/cases). */
export function CasesPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");

  const cases = useApi(() => api.cases({ state: stateFilter || undefined, limit: 200 }), [stateFilter]);
  const rows = cases.data ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (c) =>
        c.case_id.toLowerCase().includes(q) ||
        c.title.toLowerCase().includes(q) ||
        c.subject_account_key.toLowerCase().includes(q) ||
        (c.assigned_to ?? "").toLowerCase().includes(q),
    );
  }, [rows, search]);

  const columns: Column<ApiCase>[] = [
    {
      key: "case_id",
      header: "Mã vụ việc",
      render: (c) => <span className="tabular font-medium text-info">{c.case_id}</span>,
    },
    { key: "title", header: "Tiêu đề", render: (c) => <span className="text-ink-hi">{c.title}</span> },
    {
      key: "account",
      header: "Tài khoản chủ thể",
      render: (c) => <span className="tabular text-ink-mid">{c.subject_account_key}</span>,
    },
    {
      key: "state",
      header: "Trạng thái",
      render: (c) => <StatusBadge tone={stateTone(c.state)} label={caseStateLabel(c.state)} />,
    },
    { key: "risk", header: "Rủi ro", render: (c) => <RiskBadge score={Math.round(num(c.risk_score))} /> },
    {
      key: "priority",
      header: "Ưu tiên",
      render: (c) => <StatusBadge tone={PRIORITY_TONE[c.priority] ?? "muted"} label={priorityLabel(c.priority)} />,
    },
    {
      key: "alerts",
      header: "Cảnh báo",
      render: (c) => <span className="tabular text-ink-mid">{c.alert_count}</span>,
    },
    {
      key: "assigned",
      header: "Phụ trách",
      render: (c) => <span className="text-ink-mid">{c.assigned_to ?? "Chưa giao"}</span>,
    },
    {
      key: "created",
      header: "Mở lúc",
      render: (c) => <span className="tabular text-ink-mid">{formatDateTime(c.created_at)}</span>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      <PageHeader
        title="Hồ sơ vụ việc"
        subtitle="Cảnh báo được gom theo chủ thể thành vụ việc; mỗi vụ việc đi qua máy trạng thái 12 bước."
        actions={
          <button
            type="button"
            onClick={cases.reload}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
          >
            <RefreshCw size={12} aria-hidden />
            Làm mới
          </button>
        }
      />
      <Panel
        padded={false}
        title={
          <div className="flex flex-wrap items-center gap-3">
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Tìm mã vụ việc, tiêu đề, tài khoản..."
              className="w-80 font-normal"
            />
            <select
              value={stateFilter}
              onChange={(e) => setStateFilter(e.target.value)}
              aria-label="Lọc theo trạng thái"
              className="rounded-control border border-line bg-elev px-2 py-1.5 text-2xs text-ink-hi focus:outline-none"
            >
              <option value="">Tất cả trạng thái</option>
              {CASE_STATES.map((state) => (
                <option key={state} value={state}>
                  {caseStateLabel(state)}
                </option>
              ))}
            </select>
          </div>
        }
        action={<span className="tabular text-2xs text-ink-low">{filtered.length} vụ việc</span>}
      >
        {cases.loading && <LoadingSkeleton rows={5} />}
        {cases.error && <ErrorState detail={cases.error} onRetry={cases.reload} />}
        {!cases.loading &&
          !cases.error &&
          (filtered.length === 0 ? (
            <EmptyState detail="Không có vụ việc nào khớp bộ lọc." />
          ) : (
            <DataTable
              columns={columns}
              rows={filtered}
              rowKey={(c) => c.case_id}
              onRowClick={(c) => navigate(`/cases/${c.case_id}`)}
            />
          ))}
      </Panel>
    </div>
  );
}
