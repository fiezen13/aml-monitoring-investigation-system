import { AlertTriangle, BellPlus, BrainCircuit, Gauge } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { api, num } from "../api/client";
import { alertStatusLabel, detectorLabel, formatRelative, initials } from "../api/format";
import { useApi } from "../api/useApi";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { KPIStatCard } from "../components/common/KPIStatCard";
import { Panel } from "../components/common/Panel";
import { SearchInput } from "../components/common/SearchInput";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { DataTable, type Column } from "../components/tables/DataTable";
import type { ApiAlert } from "../api/client";

const ALERT_STATUS_TONE: Record<string, "warn" | "muted" | "risk" | "ok"> = {
  open: "risk",
  grouped: "warn",
  closed: "ok",
};

const DETECTOR_TONE: Record<string, "info" | "primary" | "muted"> = {
  rule: "muted",
  ml: "primary",
  graph: "info",
};

const RISK_BANDS = [
  { name: "Cao (≥75)", color: "#EF4444", test: (s: number) => s >= 75 },
  { name: "Trung bình (50–74)", color: "#F59E0B", test: (s: number) => s >= 50 && s < 75 },
  { name: "Thấp (<50)", color: "#22C55E", test: (s: number) => s < 50 },
];

export function AlertsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [typology, setTypology] = useState("");

  const alerts = useApi(() => api.alerts({ typology_code: typology || undefined, limit: 200 }), [typology]);
  const dashboard = useApi(() => api.dashboard(), []);

  const rows = alerts.data ?? [];

  // Lọc theo từ khoá ở phía trình duyệt: tập cảnh báo trong một phiên điều
  // tra nhỏ, một vòng gọi lại máy chủ cho mỗi ký tự gõ vào không đáng.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (a) =>
        a.alert_id.toLowerCase().includes(q) ||
        a.customer_id.toLowerCase().includes(q) ||
        a.account_key.toLowerCase().includes(q) ||
        a.occupation.toLowerCase().includes(q) ||
        a.typology_label.toLowerCase().includes(q),
    );
  }, [rows, search]);

  const riskDistribution = useMemo(
    () =>
      RISK_BANDS.map((band) => ({
        ...band,
        value: rows.filter((a) => band.test(num(a.risk_score))).length,
      })).filter((band) => band.value > 0),
    [rows],
  );

  const columns: Column<ApiAlert>[] = [
    {
      key: "alert_id",
      header: "Mã cảnh báo",
      render: (a) => <span className="tabular font-medium text-info">{a.alert_id}</span>,
    },
    {
      key: "subject",
      header: "Chủ thể",
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
            {initials(a.customer_id)}
          </span>
          <span>
            <span className="tabular block text-[13px] text-ink-hi">{a.customer_id}</span>
            <span className="block text-2xs text-ink-mid">{a.occupation}</span>
          </span>
        </span>
      ),
    },
    {
      key: "account",
      header: "Tài khoản",
      render: (a) => <span className="tabular text-ink-mid">{a.account_key}</span>,
    },
    {
      key: "risk",
      header: "Điểm rủi ro",
      render: (a) => <RiskBadge score={Math.round(num(a.risk_score))} />,
    },
    {
      key: "detector",
      header: "Bộ phát hiện",
      render: (a) => <StatusBadge tone={DETECTOR_TONE[a.detector] ?? "muted"} label={detectorLabel(a.detector)} />,
    },
    {
      key: "typology",
      header: "Typology",
      render: (a) => (
        <span className="text-ink-mid" title={`${a.typology_code} — gợi ý của hệ thống, cần con người rà soát`}>
          {a.typology_label}
        </span>
      ),
    },
    {
      key: "factors",
      header: "Yếu tố",
      render: (a) => (
        <span className="tabular text-ink-mid" title="NT7 — mỗi điểm rủi ro kèm tối thiểu ba yếu tố đóng góp">
          {a.factor_count}
        </span>
      ),
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (a) => (
        <StatusBadge tone={ALERT_STATUS_TONE[a.status] ?? "muted"} label={alertStatusLabel(a.status)} />
      ),
    },
    {
      key: "created",
      header: "Phát sinh",
      render: (a) => <span className="text-ink-mid">{formatRelative(a.created_at)}</span>,
    },
    {
      key: "action",
      header: "Hành động",
      render: () => <span className="font-medium text-primary">Xem chi tiết</span>,
    },
  ];

  const d = dashboard.data;

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <KPIStatCard
          label="Cảnh báo chưa đóng"
          value={d ? String(d.open_alerts) : "—"}
          icon={<BellPlus size={14} aria-hidden />}
          note="Đếm trực tiếp từ bảng alert"
        />
        <KPIStatCard
          label="Rủi ro cao (≥80)"
          value={d ? String(d.high_risk_alerts) : "—"}
          icon={<AlertTriangle size={14} aria-hidden />}
          note="Ngưỡng điểm 80/100"
        />
        <KPIStatCard
          label="Điểm rủi ro trung bình"
          value={d ? d.avg_risk_score.toFixed(1) : "—"}
          icon={<Gauge size={14} aria-hidden />}
          note="Trung bình toàn bộ cảnh báo"
        />
        <KPIStatCard
          label="Vụ việc đang điều tra"
          value={d ? String(d.cases_investigating) : "—"}
          icon={<BrainCircuit size={14} aria-hidden />}
          note="Chưa xuất hồ sơ, chưa đóng"
        />
      </div>

      <Panel
        padded={false}
        title={
          <div className="flex flex-wrap items-center gap-3">
            <span>Hàng đợi cảnh báo</span>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Tìm mã cảnh báo, chủ thể, tài khoản, typology..."
              className="w-72 font-normal"
            />
          </div>
        }
        action={
          <label className="flex items-center gap-1.5 text-2xs text-ink-low">
            Typology
            <select
              value={typology}
              onChange={(e) => setTypology(e.target.value)}
              className="rounded-control border border-line bg-elev px-1.5 py-1 text-2xs text-ink-hi focus:outline-none"
            >
              <option value="">Tất cả</option>
              {(d?.typology_distribution ?? []).map((t) => (
                <option key={t.typology_code} value={t.typology_code}>
                  {t.typology_code} — {t.typology_label}
                </option>
              ))}
            </select>
          </label>
        }
      >
        {alerts.loading && <LoadingSkeleton rows={6} />}
        {alerts.error && <ErrorState detail={alerts.error} onRetry={alerts.reload} />}
        {!alerts.loading &&
          !alerts.error &&
          (filtered.length === 0 ? (
            <EmptyState
              detail={search ? `Không có cảnh báo nào khớp "${search}".` : "Chưa có cảnh báo nào trong hệ thống."}
            />
          ) : (
            <>
              <DataTable
                columns={columns}
                rows={filtered}
                rowKey={(a) => a.alert_id}
                onRowClick={(a) => navigate(`/alerts/${a.alert_id}`)}
              />
              <div className="border-t border-line px-3 py-2 text-2xs text-ink-low">
                Hiển thị {filtered.length} trong số {rows.length} cảnh báo
              </div>
            </>
          ))}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Phân bổ theo dải rủi ro">
          {riskDistribution.length === 0 ? (
            <EmptyState title="Chưa có dữ liệu" detail="Không có cảnh báo nào để phân bổ." />
          ) : (
            <div className="flex items-center gap-4">
              <div className="relative h-32 w-32 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={riskDistribution}
                      dataKey="value"
                      innerRadius={42}
                      outerRadius={58}
                      strokeWidth={0}
                      isAnimationActive={false}
                    >
                      {riskDistribution.map((band) => (
                        <Cell key={band.name} fill={band.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="tabular text-[18px] font-bold text-ink-hi">{rows.length}</span>
                  <span className="text-2xs uppercase text-ink-low">Tổng</span>
                </div>
              </div>
              <ul className="space-y-2 text-2xs">
                {riskDistribution.map((band) => (
                  <li key={band.name} className="flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full" style={{ background: band.color }} aria-hidden />
                    <span className="text-ink-mid">{band.name}</span>
                    <span className="tabular font-semibold text-ink-hi">
                      {band.value} ({Math.round((band.value / (rows.length || 1)) * 100)}%)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <Panel title="Phân bổ theo typology">
          {!d ? (
            <LoadingSkeleton rows={4} />
          ) : (
            <div className="space-y-3">
              {d.typology_distribution.map((t) => (
                <div key={t.typology_code}>
                  <div className="mb-1 flex items-center justify-between text-2xs">
                    <span className="text-ink-mid">
                      <span className="tabular font-semibold text-ink-hi">{t.typology_code}</span> {t.typology_label}
                    </span>
                    <span className="tabular font-semibold text-ink-hi">
                      {t.alert_count} ({t.share_pct}%)
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded bg-elev">
                    <div className="h-full rounded bg-primary" style={{ width: `${t.share_pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <p className="px-1 text-2xs text-ink-low">
        Chủ thể được định danh bằng mã khách hàng và mô tả nghề nghiệp — lược đồ cố ý không lưu họ tên vì đây
        là dữ liệu tổng hợp, không phải khách hàng thật.
      </p>
    </div>
  );
}
