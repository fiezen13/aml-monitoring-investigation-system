import { AlertTriangle, BellPlus, BrainCircuit, Gauge, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { caseDisplayTitle, caseStateLabel, datasetLabel, formatDateTime, formatRelative, priorityLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";
import { useConsole } from "../context/ConsoleContext";
import { MetricCard, PageShell } from "../components/ui";
import { RISK_THRESHOLDS } from "../design/risk";
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
  const { dataset } = useConsole();
  const { currentUser } = useApp();
  const [search, setSearch] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  // Bộ lọc phụ trách: hàng nghìn vụ thì analyst cần "của tôi" và "chưa giao"
  // ngay, không phải cuộn cả bảng để tìm việc của mình.
  const [assignFilter, setAssignFilter] = useState<"" | "mine" | "unassigned">("");

  const cases = useApi(
    () => api.cases({ state: stateFilter || undefined, dataset, limit: 200 }),
    [stateFilter, dataset],
    `cases:${dataset}:${stateFilter}`,
  );
  const rows = cases.data ?? [];
  // Ngữ cảnh phễu (trước đây ở trang Trung tâm cảnh báo, nay đã gộp vào đây):
  // tổng tín hiệu thô, rủi ro cao, điểm TB, và số vụ đang điều tra.
  const dashboard = useApi(() => api.dashboard({ dataset: dataset || undefined }), [dataset], `dashboard:${dataset}`);
  const d = dashboard.data;

  // Khớp "của tôi" theo tên/email/id vì `assigned_to` có thể lưu ở dạng bất kỳ.
  const isMine = (assigned: string | null): boolean => {
    if (!assigned || !currentUser) return false;
    const a = assigned.trim().toLowerCase();
    return [currentUser.name, currentUser.email, currentUser.id]
      .filter(Boolean)
      .some((v) => v!.toLowerCase() === a);
  };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rows.filter((c) => {
      if (assignFilter === "unassigned" && c.assigned_to) return false;
      if (assignFilter === "mine" && !isMine(c.assigned_to)) return false;
      if (!q) return true;
      return (
        c.case_id.toLowerCase().includes(q) ||
        c.title.toLowerCase().includes(q) ||
        c.subject_account_key.toLowerCase().includes(q) ||
        (c.assigned_to ?? "").toLowerCase().includes(q)
      );
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, search, assignFilter, currentUser]);

  const columns: Column<ApiCase>[] = [
    {
      key: "case_id",
      header: "Mã vụ việc",
      render: (c) => <span className="tabular font-medium text-info">{c.case_id}</span>,
    },
    {
      key: "title",
      header: "Tiêu đề",
      // Tên nghiệp vụ theo chủ thể thay cho "Explainable investigation for
      // ALERT-…"; giữ tiêu đề gốc trong tooltip cho ai cần.
      render: (c) => (
        <span className="text-ink-hi" title={c.title}>
          {caseDisplayTitle(c.title, c.subject_account_key)}
        </span>
      ),
    },
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
      header: "Tuổi hồ sơ",
      // Tuổi vụ (thời gian tương đối) giúp ưu tiên nhanh hơn dấu thời gian tuyệt
      // đối; ngày giờ đầy đủ vẫn xem được ở tooltip.
      render: (c) => (
        <span className="tabular text-ink-mid" title={`Mở lúc ${formatDateTime(c.created_at)}`}>
          {formatRelative(c.created_at)}
        </span>
      ),
    },
  ];

  return (
    <PageShell>
      <PageHeader
        title="Vụ việc"
        subtitle={`Bộ dữ liệu ${datasetLabel(dataset)} · trung tâm điều tra — cảnh báo được sàng và gom theo chủ thể thành vụ việc; bạn làm việc trên vụ (điều tra AI, đồ thị, SAR) ngay tại đây.`}
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

      {/* Ngữ cảnh phễu gộp từ trang Trung tâm cảnh báo cũ: cảnh báo thô là tín
          hiệu, không phải nơi làm việc — hệ thống tự sàng/gom thành vụ. Bốn thẻ
          này cho thấy khối lượng tín hiệu đứng sau số vụ đang mở. */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard
          label="Cảnh báo chưa đóng"
          value={d ? d.open_alerts : "—"}
          icon={<BellPlus size={14} aria-hidden />}
          note="Tín hiệu thô, hệ thống tự sàng thành vụ"
        />
        <MetricCard
          label={`Rủi ro cao (≥${RISK_THRESHOLDS.critical})`}
          value={d ? d.high_risk_alerts : "—"}
          tone="risk"
          icon={<AlertTriangle size={14} aria-hidden />}
          note={`Ngưỡng điểm ${RISK_THRESHOLDS.critical}/100`}
        />
        <MetricCard
          label="Điểm rủi ro trung bình"
          value={d ? d.avg_risk_score.toFixed(1) : "—"}
          icon={<Gauge size={14} aria-hidden />}
          note="Trung bình toàn bộ cảnh báo"
        />
        <MetricCard
          label="Vụ việc đang điều tra"
          value={d ? d.cases_investigating : "—"}
          tone="agent"
          icon={<BrainCircuit size={14} aria-hidden />}
          note="Chưa xuất hồ sơ, chưa đóng"
        />
      </div>
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
            <div className="inline-flex overflow-hidden rounded-control border border-line text-2xs">
              {(
                [
                  ["", "Tất cả"],
                  ["mine", "Của tôi"],
                  ["unassigned", "Chưa giao"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value || "all"}
                  type="button"
                  onClick={() => setAssignFilter(value)}
                  className={`px-2.5 py-1.5 font-medium transition-colors ${
                    assignFilter === value
                      ? "bg-primary text-app"
                      : "bg-elev text-ink-mid hover:text-ink-hi"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
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

      <p className="text-meta leading-relaxed text-ink-low">
        <b className="text-ink-mid">Rủi ro</b> phản ánh mức đáng ngờ của chủ thể/hành vi; <b className="text-ink-mid">Ưu tiên</b>{" "}
        phản ánh mức cần xử lý trước, tính từ rủi ro cùng với SLA, mức phơi nhiễm và bối cảnh pháp lý — nên hai cột có thể
        khác nhau. <b className="text-ink-mid">Cảnh báo</b> là số tín hiệu đã gom vào vụ; một vụ nên gom mọi cảnh báo liên
        quan của cùng chủ thể/bối cảnh điều tra.
      </p>
    </PageShell>
  );
}
