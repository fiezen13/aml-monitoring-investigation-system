import {
  AlertTriangle,
  BellPlus,
  BrainCircuit,
  Plus,
  Timer,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Cell,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import { ConfidenceBadge, RiskBadge, StatusBadge } from "../components/common/Badges";
import { FilterBar } from "../components/common/FilterBar";
import { KPIStatCard } from "../components/common/KPIStatCard";
import { Pagination } from "../components/common/Pagination";
import { Panel } from "../components/common/Panel";
import { ReasonModal } from "../components/common/ReasonModal";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { DataTable, type Column } from "../components/tables/DataTable";
import { useApp } from "../context/AppContext";
import { ALERTS } from "../data/mockAlerts";
import type { Alert } from "../types";

const RISK_DIST = [
  { name: "Cao", value: 126, color: "#EF4444" },
  { name: "Trung bình", value: 398, color: "#F59E0B" },
  { name: "Thấp", value: 724, color: "#22C55E" },
];

const RADAR_DATA = [
  { axis: "Structuring", value: 82 },
  { axis: "Velocity", value: 56 },
  { axis: "Sanctions", value: 44 },
  { axis: "Geographic", value: 30 },
  { axis: "PEP Match", value: 61 },
];

type DemoState = "normal" | "loading" | "empty" | "error";

const STATUS_TONE: Record<Alert["status"], "warn" | "muted" | "risk" | "ok"> = {
  in_progress: "warn",
  open: "muted",
  urgent: "risk",
  resolved: "ok",
};

export function AlertsPage() {
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [demoState, setDemoState] = useState<DemoState>("normal");
  const [chipFilters, setChipFilters] = useState<Record<string, boolean>>({
    critical: true,
    structuring: true,
  });
  const [createOpen, setCreateOpen] = useState(false);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return ALERTS.filter(
      (a) =>
        !q ||
        a.alert_id.toLowerCase().includes(q) ||
        a.customer.name.toLowerCase().includes(q) ||
        a.typology_label.toLowerCase().includes(q),
    );
  }, [search]);

  const columns: Column<Alert>[] = [
    {
      key: "id",
      header: (
        <span className="inline-flex items-center gap-2">
          <input type="checkbox" aria-label="Chọn tất cả" className="accent-[#00B2A9]" onClick={(e) => e.stopPropagation()} />
          Mã cảnh báo
        </span>
      ),
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            aria-label={`Chọn ${a.alert_id}`}
            className="accent-[#00B2A9]"
            onClick={(e) => e.stopPropagation()}
          />
          <span className="tabular font-medium text-info">{a.alert_id}</span>
        </span>
      ),
    },
    {
      key: "customer",
      header: "Khách hàng",
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
            {a.customer.initials}
          </span>
          {a.customer.name}
        </span>
      ),
    },
    { key: "risk", header: "Điểm rủi ro", render: (a) => <RiskBadge score={a.risk_score} /> },
    {
      key: "confidence",
      header: "Độ tin cậy AI",
      render: (a) => <ConfidenceBadge value={a.ai_confidence} />,
    },
    {
      key: "typology",
      header: "Typology",
      render: (a) => (
        <span
          className="text-ink-mid"
          title={`Typology được gợi ý: ${a.typology_code} — cần con người rà soát`}
        >
          {a.typology_label}
        </span>
      ),
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (a) => <StatusBadge tone={STATUS_TONE[a.status]} label={a.statusLabel} />,
    },
    {
      key: "sla",
      header: "SLA",
      render: (a) =>
        a.slaOverdue ? (
          <span className="tabular font-semibold text-risk underline decoration-risk/60">
            QUÁ HẠN
          </span>
        ) : (
          <span className={`tabular ${a.sla.includes("còn lại") ? "text-warn" : "text-ink-mid"}`}>
            {a.sla}
          </span>
        ),
    },
    {
      key: "action",
      header: "Hành động",
      render: () => <span className="font-medium text-primary">Xem chi tiết</span>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
      {/* Hàng KPI */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KPIStatCard
          label="Tổng cảnh báo mới"
          value="1,248"
          icon={<BellPlus size={14} aria-hidden />}
          trend={{ value: "+18.6% so với 7 ngày qua", direction: "up", tone: "good" }}
          spark={[3, 4, 3, 5, 6, 5, 8]}
        />
        <KPIStatCard
          label="Rủi ro cao (Critical)"
          value="126"
          icon={<AlertTriangle size={14} aria-hidden />}
          trend={{ value: "+22.4% so với 7 ngày qua", direction: "up", tone: "bad" }}
          spark={[2, 3, 2, 4, 3, 5, 6]}
          sparkColor="#EF4444"
        />
        <KPIStatCard
          label="Độ tin cậy AI trung bình"
          value="92.4%"
          icon={<BrainCircuit size={14} aria-hidden />}
          trend={{ value: "Ổn định (±0.2%)", direction: "up", tone: "good" }}
          spark={[5, 5, 6, 5, 6, 6, 6]}
        />
        <KPIStatCard
          label="SLA trung bình"
          value="1.4h"
          icon={<Timer size={14} aria-hidden />}
          trend={{ value: "-12% thời gian xử lý", direction: "down", tone: "good" }}
          spark={[8, 7, 6, 6, 5, 4, 4]}
          sparkColor="#F59E0B"
        />
      </div>

      <FilterBar
        dateLabel="12 May - 19 May, 2026"
        onAdvanced={() => pushToast({ tone: "info", title: "Bộ lọc nâng cao (mô phỏng)" })}
        onExport={() => pushToast({ tone: "success", title: "Đã xuất báo cáo hàng đợi (mô phỏng)" })}
        chips={[
          {
            id: "critical",
            label: "Critical",
            active: chipFilters.critical,
            tone: "risk",
            onToggle: (id) => setChipFilters((f) => ({ ...f, [id]: !f[id] })),
          },
          {
            id: "structuring",
            label: "Structuring",
            active: chipFilters.structuring,
            onToggle: (id) => setChipFilters((f) => ({ ...f, [id]: !f[id] })),
          },
          { id: "more", label: "+3 more", active: false, onToggle: () => undefined },
        ]}
        trailing={
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover"
          >
            <Plus size={12} aria-hidden />
            Tạo vụ việc mới
          </button>
        }
      />

      {/* Bảng cảnh báo */}
      <Panel
        padded={false}
        title={
          <div className="flex items-center gap-3">
            <span>Danh sách cảnh báo</span>
            <SearchInput
              value={search}
              onChange={(v) => {
                setSearch(v);
                setPage(1);
              }}
              placeholder="Tìm kiếm mã, khách hàng, typology..."
              className="w-72 font-normal"
              shortcutHint="⌘K"
            />
          </div>
        }
        action={
          <label className="flex items-center gap-1.5 text-2xs text-ink-low">
            Trạng thái demo
            <select
              value={demoState}
              onChange={(e) => setDemoState(e.target.value as DemoState)}
              className="rounded-control border border-line bg-elev px-1.5 py-1 text-2xs text-ink-hi focus:outline-none"
            >
              <option value="normal">Bình thường</option>
              <option value="loading">Đang tải</option>
              <option value="empty">Không có dữ liệu</option>
              <option value="error">Lỗi tải dữ liệu</option>
            </select>
          </label>
        }
      >
        {demoState === "loading" && <LoadingSkeleton rows={5} />}
        {demoState === "empty" && <EmptyState />}
        {demoState === "error" && (
          <ErrorState onRetry={() => setDemoState("normal")} />
        )}
        {demoState === "normal" &&
          (filtered.length === 0 ? (
            <EmptyState detail={`Không có cảnh báo nào khớp "${search}".`} />
          ) : (
            <>
              <DataTable
                columns={columns}
                rows={filtered}
                rowKey={(a) => a.alert_id}
                onRowClick={(a) => navigate(`/alerts/${a.alert_id}`)}
              />
              <div className="border-t border-line px-2">
                <Pagination
                  page={page}
                  pageCount={250}
                  onChange={setPage}
                  summary={`Hiển thị 1-${filtered.length} trong số 1,248 cảnh báo`}
                />
              </div>
            </>
          ))}
      </Panel>

      {/* Hàng dưới: donut + radar + AI insight */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Panel title="Phân bổ rủi ro">
          <div className="flex items-center gap-4">
            <div className="relative h-32 w-32 shrink-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={RISK_DIST}
                    dataKey="value"
                    innerRadius={42}
                    outerRadius={58}
                    strokeWidth={0}
                    isAnimationActive={false}
                  >
                    {RISK_DIST.map((d) => (
                      <Cell key={d.name} fill={d.color} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="tabular text-[18px] font-bold text-ink-hi">1.2k</span>
                <span className="text-2xs uppercase text-ink-low">Tổng</span>
              </div>
            </div>
            <ul className="space-y-2 text-2xs">
              {RISK_DIST.map((d) => (
                <li key={d.name} className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full" style={{ background: d.color }} aria-hidden />
                  <span className="text-ink-mid">{d.name}</span>
                  <span className="tabular font-semibold text-ink-hi">
                    {d.value} ({Math.round((d.value / 1248) * 100)}%)
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </Panel>

        <Panel title="Alert Typology Radar">
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={RADAR_DATA} outerRadius="75%">
                <PolarGrid stroke="rgba(148,163,184,0.18)" />
                <PolarAngleAxis
                  dataKey="axis"
                  tick={{ fill: "#64748B", fontSize: 9 }}
                />
                <Radar
                  dataKey="value"
                  stroke="#00B2A9"
                  fill="#00B2A9"
                  fillOpacity={0.25}
                  isAnimationActive={false}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title={
            <span className="inline-flex items-center gap-1.5">
              <BrainCircuit size={13} className="text-primary" aria-hidden />
              AI Insight Tức thì
            </span>
          }
          elevated
        >
          <div className="rounded-control border border-line bg-panel p-3 text-2xs leading-relaxed text-ink-mid">
            <span className="font-semibold text-primary">Phát hiện Structuring:</span>{" "}
            Cảnh báo ALT-2026-001 có độ tương đồng 94% với các mẫu rửa tiền đã xác nhận
            trước đây tại chi nhánh TP.HCM.
          </div>
          <button
            type="button"
            onClick={() => navigate("/alerts/ALT-2026-001")}
            className="mt-3 w-full rounded-control bg-primary py-2 text-2xs font-bold uppercase tracking-wider text-app hover:bg-primary-hover"
          >
            Phân tích sâu bằng AI
          </button>
        </Panel>
      </div>

      <ReasonModal
        open={createOpen}
        title="Tạo vụ việc mới"
        description="Vụ việc mới sẽ gom các cảnh báo được chọn theo chủ thể. Hành động này ghi vào audit trail."
        confirmLabel="Tạo vụ việc"
        onClose={() => setCreateOpen(false)}
        onConfirm={() => {
          setCreateOpen(false);
          pushToast({
            tone: "success",
            title: "Đã tạo vụ việc CASE-2026-014",
            detail: "Gom từ cảnh báo ALT-2026-001 · ghi nhật ký NT4.",
          });
          navigate("/cases/CASE-2026-014");
        }}
      />
    </div>
  );
}
