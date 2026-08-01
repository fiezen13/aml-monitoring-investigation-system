import {
  AlertTriangle,
  BellRing,
  Database,
  FileWarning,
  FolderSearch,
  Gauge,
  RefreshCw,
  Server,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { detectorLabel, formatRelative, initials } from "../api/format";
import { useApi } from "../api/useApi";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { DataTable, type Column } from "../components/tables/DataTable";
import type { ApiAlert } from "../api/client";

const TYPOLOGY_COLORS = ["#00B2A9", "#EA8458", "#EF4444", "#F59E0B", "#3B82F6", "#8B5CF6"];

export function DashboardPage() {
  const navigate = useNavigate();
  const dashboard = useApi(() => api.dashboard(), []);
  const ready = useApi(() => api.ready(), []);

  const d = dashboard.data;

  const kpis = [
    {
      label: "Cảnh báo chưa đóng",
      value: d ? String(d.open_alerts) : "—",
      icon: BellRing,
      note: "bảng alert, status ≠ closed",
    },
    {
      label: "Rủi ro cao",
      value: d ? String(d.high_risk_alerts) : "—",
      icon: AlertTriangle,
      note: "điểm rủi ro ≥ 80",
    },
    {
      label: "Vụ việc đang điều tra",
      value: d ? String(d.cases_investigating) : "—",
      icon: FolderSearch,
      note: "chưa xuất hồ sơ, chưa đóng",
    },
    {
      label: "Hồ sơ chờ duyệt",
      value: d ? String(d.sar_pending) : "—",
      icon: FileWarning,
      note: "bảng approval, decision = pending",
    },
  ];

  const alertColumns: Column<ApiAlert>[] = [
    {
      key: "alert_id",
      header: "Mã cảnh báo",
      render: (a) => <span className="tabular font-medium text-info">{a.alert_id}</span>,
    },
    {
      key: "typology",
      header: "Typology",
      render: (a) => (
        <span title={a.typology_code}>
          <span className="tabular font-semibold text-ink-hi">{a.typology_code}</span>{" "}
          <span className="text-ink-mid">{a.typology_label}</span>
        </span>
      ),
    },
    {
      key: "subject",
      header: "Chủ thể",
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
            {initials(a.customer_id)}
          </span>
          <span className="tabular">{a.customer_id}</span>
        </span>
      ),
    },
    { key: "risk", header: "Rủi ro", render: (a) => <RiskBadge score={Math.round(num(a.risk_score))} /> },
    {
      key: "detector",
      header: "Phát hiện bởi",
      render: (a) => <span className="text-ink-mid">{detectorLabel(a.detector)}</span>,
    },
    {
      key: "time",
      header: "Thời gian",
      render: (a) => <span className="text-ink-mid">{formatRelative(a.created_at)}</span>,
    },
    { key: "action", header: "Thao tác", render: () => <span className="font-medium text-primary">Xem</span> },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-hi">Trung tâm Điều hành AML</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">
            Mọi số liệu trên trang này đếm trực tiếp từ PostgreSQL tại thời điểm tải trang.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            dashboard.reload();
            ready.reload();
          }}
          className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-primary/50"
        >
          <RefreshCw size={12} aria-hidden />
          Làm mới
        </button>
      </div>

      {dashboard.error && <ErrorState detail={dashboard.error} onRetry={dashboard.reload} />}

      {!dashboard.error && (
        <>
          <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
            {kpis.map(({ label, value, note, icon: Icon }) => (
              <div key={label} className="rounded-panel border border-line bg-panel p-4">
                <div className="flex items-center justify-between">
                  <Icon size={15} className="text-ink-mid" aria-hidden />
                </div>
                <div className="mt-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{label}</div>
                <div className="tabular mt-1 text-[28px] font-bold leading-none text-ink-hi">
                  {dashboard.loading ? <span className="text-ink-low">…</span> : value}
                </div>
                <div className="mt-1.5 text-2xs text-ink-low">{note}</div>
              </div>
            ))}
          </div>

          <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_320px]">
            <div className="space-y-3">
              <Panel title="Phân bổ cảnh báo theo typology">
                {dashboard.loading && <LoadingSkeleton rows={4} />}
                {d && d.typology_distribution.length === 0 && (
                  <EmptyState title="Chưa có cảnh báo" detail="Hệ thống chưa sinh cảnh báo nào." />
                )}
                {d && d.typology_distribution.length > 0 && (
                  <>
                    <div className="space-y-3">
                      {d.typology_distribution.map((t, i) => (
                        <div key={t.typology_code}>
                          <div className="mb-1 flex items-center justify-between text-2xs">
                            <span className="text-ink-mid">
                              <span className="tabular font-semibold text-ink-hi">{t.typology_code}</span>{" "}
                              {t.typology_label}
                            </span>
                            <span className="tabular font-semibold text-ink-hi">
                              {t.alert_count} ({t.share_pct}%)
                            </span>
                          </div>
                          <div className="h-1.5 overflow-hidden rounded bg-elev">
                            <div
                              className="h-full rounded"
                              style={{
                                width: `${t.share_pct}%`,
                                background: TYPOLOGY_COLORS[i % TYPOLOGY_COLORS.length],
                              }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                    <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-2xs">
                      <span className="inline-flex items-center gap-1.5 text-ink-mid">
                        <Gauge size={12} className="text-primary" aria-hidden />
                        Điểm rủi ro trung bình
                      </span>
                      <span className="tabular text-[18px] font-bold text-ink-hi">{d.avg_risk_score}</span>
                    </div>
                  </>
                )}
              </Panel>

              <Panel
                title="Cảnh báo ưu tiên cao nhất"
                padded={false}
                action={
                  <button
                    type="button"
                    onClick={() => navigate("/alerts")}
                    className="text-2xs font-medium text-primary hover:underline"
                  >
                    Xem tất cả
                  </button>
                }
              >
                {dashboard.loading && <LoadingSkeleton rows={5} />}
                {d && d.top_alerts.length === 0 && <EmptyState title="Chưa có cảnh báo" />}
                {d && d.top_alerts.length > 0 && (
                  <DataTable
                    columns={alertColumns}
                    rows={d.top_alerts}
                    rowKey={(a) => a.alert_id}
                    onRowClick={(a) => navigate(`/alerts/${a.alert_id}`)}
                    dense
                  />
                )}
              </Panel>
            </div>

            <div className="space-y-3">
              <Panel
                title={
                  <span className="inline-flex items-center gap-1.5">
                    <Server size={13} className="text-primary" aria-hidden />
                    Tình trạng hệ thống
                  </span>
                }
              >
                <div className="space-y-2.5">
                  <StatusRow
                    label="PostgreSQL"
                    ok={ready.data?.database ?? false}
                    loading={ready.loading}
                    icon={<Database size={12} aria-hidden />}
                  />
                  <StatusRow
                    label="Redis"
                    ok={ready.data?.redis ?? false}
                    loading={ready.loading}
                    icon={<Database size={12} aria-hidden />}
                  />
                  <StatusRow
                    label="Worker nền"
                    ok={d?.worker_alive ?? false}
                    loading={dashboard.loading}
                    icon={<Server size={12} aria-hidden />}
                  />
                </div>
                <div className="mt-3 flex items-center justify-between border-t border-line pt-3 text-2xs">
                  <span className="text-ink-mid">Tác vụ đang chờ trong hàng đợi</span>
                  <span className="tabular font-bold text-ink-hi">{d ? d.queue_depth : "—"}</span>
                </div>
              </Panel>

              <Panel title="Đọc số liệu này thế nào">
                <ul className="space-y-2 text-2xs leading-relaxed text-ink-mid">
                  <li>
                    <span className="font-semibold text-ink-hi">Điểm rủi ro</span> là kết quả của bộ luật và
                    heuristic trong dữ liệu mẫu, chưa phải mô hình đã huấn luyện. Mở một cảnh báo để xem các
                    yếu tố đóng góp (NT7).
                  </li>
                  <li>
                    <span className="font-semibold text-ink-hi">Typology</span> là gợi ý của hệ thống. Mọi kết
                    luận đều cần con người rà soát trước khi vào hồ sơ.
                  </li>
                  <li>
                    <span className="font-semibold text-ink-hi">Mức rủi ro hồ sơ</span> suy ra từ nguyên mẫu và
                    quốc gia đăng ký, không suy ra từ nhãn rửa tiền (ND1).
                  </li>
                </ul>
              </Panel>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function StatusRow({
  label,
  ok,
  loading,
  icon,
}: {
  label: string;
  ok: boolean;
  loading: boolean;
  icon: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="inline-flex items-center gap-1.5 text-2xs text-ink-mid">
        <span className="text-primary">{icon}</span>
        {label}
      </span>
      {loading ? (
        <span className="text-2xs text-ink-low">đang kiểm tra…</span>
      ) : (
        <StatusBadge tone={ok ? "ok" : "risk"} label={ok ? "Hoạt động" : "Không phản hồi"} />
      )}
    </div>
  );
}
