import { AlertTriangle, BellPlus, BrainCircuit, Gauge, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { api, num } from "../api/client";
import { caseDisplayTitle, caseStateLabel, datasetLabel, formatAmount, formatDateTime, formatRelative, priorityLabel } from "../api/format";
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
import { Pagination } from "../components/common/Pagination";
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

/** Vụ đã kết thúc thì không nhận được nữa — khớp `_CLOSED_CASE_STATES` máy chủ. */
const CLOSED_STATES = new Set(["XuatHoSo", "DongKhongBaoCao"]);

const stateTone = (state: string): "ok" | "warn" | "info" | "muted" =>
  state === "XuatHoSo" ? "ok" : state === "ChoNguoiPheDuyet" ? "warn" : state === "DongKhongBaoCao" ? "muted" : "info";

/** Hàng đợi vụ việc theo điểm rủi ro giảm dần (GET /api/v1/cases). */
export function CasesPage() {
  const navigate = useNavigate();
  const { dataset } = useConsole();
  const [search, setSearch] = useState("");
  const [queryText, setQueryText] = useState("");
  const [stateFilter, setStateFilter] = useState("");
  // Bộ lọc phụ trách: hàng nghìn vụ thì analyst cần "của tôi" và "chưa giao"
  // ngay, không phải cuộn cả bảng để tìm việc của mình.
  // Nhận sẵn bộ lọc từ đường dẫn: thẻ "Phân công và khối lượng" ở Tổng quan dẫn
  // thẳng tới hàng đợi chưa ai giữ, nên link phải áp được bộ lọc.
  const [searchParams] = useSearchParams();
  const initialAssign = searchParams.get("assignment");
  const [assignFilter, setAssignFilter] = useState<"" | "mine" | "unassigned">(
    initialAssign === "mine" || initialAssign === "unassigned" ? initialAssign : "",
  );
  const [page, setPage] = useState(1);
  const pageSize = 50;

  useEffect(() => {
    const timer = window.setTimeout(() => setQueryText(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => setPage(1), [queryText, stateFilter, assignFilter, dataset]);

  const cases = useApi(
    () =>
      api.casesPage({
        state: stateFilter || undefined,
        dataset,
        q: queryText || undefined,
        assignment: assignFilter || undefined,
        page,
        page_size: pageSize,
      }),
    [stateFilter, dataset, queryText, assignFilter, page],
    `cases:${dataset}:${stateFilter}:${queryText}:${assignFilter}:${page}`,
  );
  const { currentUser, pushToast } = useApp();
  const isAnalyst = currentUser?.role === "analyst";
  const [claiming, setClaiming] = useState<string | null>(null);
  const claim = async (caseId: string) => {
    setClaiming(caseId);
    try {
      await api.assignCase(caseId, currentUser?.id ?? null, "Chuyên viên tự nhận vụ từ hàng đợi");
      await cases.reload();
      pushToast({ tone: "success", title: "Đã nhận vụ việc", detail: `${caseId} nay thuộc phần việc của bạn.` });
    } catch (cause) {
      pushToast({
        tone: "error",
        title: "Không nhận được vụ việc",
        detail: cause instanceof Error ? cause.message : "Lỗi không xác định",
      });
    } finally {
      setClaiming(null);
    }
  };

  const rows = cases.data?.rows ?? [];
  const total = cases.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  // Cảnh báo đã được chuyển thành vụ việc trước khi chuyên viên mở màn hình.
  // Các thẻ vì vậy chỉ nói về hồ sơ nghiệp vụ, không dựng lại hàng đợi cảnh báo.
  const dashboard = useApi(() => api.dashboard({ dataset: dataset || undefined }), [dataset], `dashboard:${dataset}`);
  const d = dashboard.data;

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
      // QUY MÔ — cột này tồn tại vì điểm rủi ro bão hoà ở 100.
      //
      // 7.226 tài khoản có điểm đúng 100, và đo trên nhãn thật thì cả 7.226 đều
      // trúng: mô hình không sai. Nhưng chuyên viên nhìn một cột toàn số 100 thì
      // không biết làm vụ nào trước. Hai con số này là sự thật đo được về tài
      // khoản, tách khối bão hoà thành 5.573 nhóm phân biệt được.
      key: "scale",
      header: "Quy mô",
      render: (c) =>
        c.flagged_amount == null ? (
          <span className="text-2xs text-ink-low">—</span>
        ) : (
          <div className="text-2xs leading-tight">
            <div className="tabular text-ink-hi">{formatAmount(num(c.flagged_amount))}</div>
            <div className="text-ink-mid">{c.flagged_txn_count} giao dịch bị gắn cờ</div>
          </div>
        ),
    },
    {
      key: "priority",
      header: "Ưu tiên",
      render: (c) => <StatusBadge tone={PRIORITY_TONE[c.priority] ?? "muted"} label={priorityLabel(c.priority)} />,
    },
    {
      key: "assigned",
      header: "Phụ trách",
      // Chuyên viên nhận việc NGAY TRÊN HÀNG ĐỢI: bắt mở từng vụ mới nhận được
      // thì lọc "chưa giao" chẳng giúp gì cho việc chia việc hàng ngày.
      render: (c) =>
        c.assigned_name ? (
          <span className="text-ink-mid">{c.assigned_name}</span>
        ) : isAnalyst && !CLOSED_STATES.has(c.state) ? (
          <button
            type="button"
            disabled={claiming === c.case_id}
            onClick={(event) => {
              event.stopPropagation();
              void claim(c.case_id);
            }}
            className="rounded-control border border-line px-2 py-0.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis disabled:opacity-50"
          >
            {claiming === c.case_id ? "Đang nhận…" : "Nhận vụ"}
          </button>
        ) : (
          <span className="text-ink-low">Chưa giao</span>
        ),
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
        subtitle={`Bộ dữ liệu ${datasetLabel(dataset)} · hệ thống đã mở sẵn một vụ việc cho mỗi cảnh báo. Chuyên viên chỉ gọi AI sau khi chọn hồ sơ cần điều tra.`}
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

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard
          label="Vụ việc đang mở"
          value={d ? d.cases_total : "—"}
          icon={<BellPlus size={14} aria-hidden />}
          note="Đã tạo hồ sơ trước bước gọi AI"
        />
        <MetricCard
          label={`Vụ rủi ro nghiêm trọng (≥${RISK_THRESHOLDS.critical})`}
          value={d ? d.high_risk_alerts : "—"}
          tone="risk"
          icon={<AlertTriangle size={14} aria-hidden />}
          note={`Ngưỡng điểm ${RISK_THRESHOLDS.critical}/100`}
        />
        <MetricCard
          label="Điểm rủi ro trung bình"
          value={d ? d.avg_risk_score.toFixed(1) : "—"}
          icon={<Gauge size={14} aria-hidden />}
          note="Trung bình toàn bộ vụ việc đang mở"
        />
        <MetricCard
          label="Chờ chuyên viên rà soát"
          value={d ? d.cases_awaiting_review : "—"}
          tone="agent"
          icon={<BrainCircuit size={14} aria-hidden />}
          note="Chưa khởi chạy điều tra AI"
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
        action={<span className="tabular text-2xs text-ink-low">{total} vụ việc</span>}
      >
        {cases.loading && <LoadingSkeleton rows={5} />}
        {cases.error && <ErrorState detail={cases.error} onRetry={cases.reload} />}
        {!cases.loading &&
          !cases.error &&
          (rows.length === 0 ? (
            <EmptyState detail="Không có vụ việc nào khớp bộ lọc." />
          ) : (
            <>
              <DataTable
                columns={columns}
                rows={rows}
                rowKey={(c) => c.case_id}
                onRowClick={(c) => navigate(`/cases/${c.case_id}`)}
              />
              <Pagination
                page={page}
                pageCount={pageCount}
                onChange={setPage}
                summary={`Hiển thị ${Math.min((page - 1) * pageSize + 1, total)}–${Math.min(page * pageSize, total)} trong ${total} vụ việc`}
              />
            </>
          ))}
      </Panel>

      <p className="text-meta leading-relaxed text-ink-low">
        <b className="text-ink-mid">Rủi ro</b> phản ánh mức đáng ngờ của chủ thể/hành vi; <b className="text-ink-mid">Ưu tiên</b>{" "}
        phản ánh mức cần xử lý trước, tính từ rủi ro cùng với SLA, mức phơi nhiễm và bối cảnh pháp lý — nên hai cột có thể
        khác nhau. Mỗi cảnh báo đã có sẵn một hồ sơ vụ việc; mở hồ sơ không làm AI chạy. Chuyên viên chỉ khởi động AI sau
        khi đã chọn vụ cần phân tích.
      </p>
    </PageShell>
  );
}
