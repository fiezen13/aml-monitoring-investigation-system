import {
  AlertTriangle,
  BellRing,
  Calendar,
  FileWarning,
  Filter,
  FolderSearch,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { RiskBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { Tabs } from "../components/common/Tabs";
import { DataTable, type Column } from "../components/tables/DataTable";
import { useApp } from "../context/AppContext";
import { useState } from "react";

interface PriorityAlertRow {
  id: string;
  typology: string;
  customer: string;
  risk: number;
  time: string;
}

const PRIORITY_ALERTS: PriorityAlertRow[] = [
  { id: "ALT-78491", typology: "Structuring", customer: "Michael Johnson", risk: 89, time: "2 phút trước" },
  { id: "ALT-78490", typology: "High Velocity", customer: "Global Tech Ltd.", risk: 75, time: "5 phút trước" },
  { id: "ALT-78489", typology: "Sanctions Match", customer: "Maria Garcia", risk: 92, time: "12 phút trước" },
  { id: "ALT-78488", typology: "PEP Match", customer: "Ahmed Hassan", risk: 65, time: "18 phút trước" },
  { id: "ALT-78487", typology: "Unusual Pattern", customer: "Sophia Williams", risk: 60, time: "25 phút trước" },
];

const TYPOLOGY_DIST = [
  { label: "Structuring (Gom lẻ)", pct: 45, color: "#00B2A9" },
  { label: "Shell Companies (Công ty vỏ bọc)", pct: 28, color: "#EA8458" },
  { label: "High Velocity (Tốc độ cao)", pct: 15, color: "#EF4444" },
];

const COMPLIANCE = [
  { label: "KYC Compliance", pct: 98.2, icon: ShieldCheck },
  { label: "Sanctions Screening", pct: 94.7, icon: ShieldCheck },
  { label: "PEP Screening", pct: 96.3, icon: ShieldCheck },
];

/** Bản đồ mật độ rủi ro — chấm teal rải trên lưới, thay cho ảnh bản đồ stock. */
function RiskDensityMap() {
  const dots: { x: number; y: number; r: number; o: number }[] = [];
  let seed = 42;
  const rand = () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
  for (let i = 0; i < 140; i++) {
    dots.push({ x: 4 + rand() * 292, y: 8 + rand() * 104, r: rand() * 1.8 + 0.6, o: rand() * 0.7 + 0.15 });
  }
  return (
    <svg viewBox="0 0 300 120" className="h-full w-full" role="img" aria-label="Mật độ rủi ro toàn cầu">
      <rect width="300" height="120" fill="#06111D" rx="6" />
      {dots.map((d, i) => (
        <circle key={i} cx={d.x} cy={d.y} r={d.r} fill="#00B2A9" opacity={d.o} />
      ))}
    </svg>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const [trendTab, setTrendTab] = useState("week");

  const kpis = [
    { label: "Cảnh báo chưa xử lý", value: "12", trend: "+18.6%", tone: "text-ok", icon: BellRing },
    { label: "Rủi ro cao", value: "5", trend: "+22.4%", tone: "text-risk", icon: AlertTriangle },
    { label: "Vụ việc đang điều tra", value: "8", trend: "+14.8%", tone: "text-ok", icon: FolderSearch },
    { label: "SAR chờ duyệt", value: "3", trend: "+6.7%", tone: "text-ok", icon: FileWarning },
  ];

  const alertColumns: Column<PriorityAlertRow>[] = [
    {
      key: "id",
      header: "ID cảnh báo",
      render: (r) => <span className="tabular font-medium text-info">{r.id}</span>,
    },
    { key: "typology", header: "Loại hình", render: (r) => r.typology },
    { key: "customer", header: "Khách hàng", render: (r) => r.customer },
    {
      key: "risk",
      header: "Rủi ro",
      render: (r) => <RiskBadge score={r.risk} />,
    },
    { key: "time", header: "Thời gian", render: (r) => <span className="text-ink-mid">{r.time}</span> },
    {
      key: "action",
      header: "Thao tác",
      render: () => <span className="font-medium text-primary">Xem</span>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-hi">Trung tâm Điều hành AML</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">
            Theo dõi thời gian thực tội phạm tài chính và các hoạt động đáng ngờ.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi"
          >
            <Calendar size={12} aria-hidden />
            May 12 - May 19, 2026
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi"
          >
            <Filter size={12} aria-hidden />
            Bộ lọc
          </button>
        </div>
      </div>

      {/* Hàng KPI */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {kpis.map(({ label, value, trend, tone, icon: Icon }) => (
          <div key={label} className="rounded-panel border border-line bg-panel p-4">
            <div className="flex items-center justify-between">
              <Icon size={15} className="text-ink-mid" aria-hidden />
              <span className={`tabular text-2xs font-semibold ${tone}`}>↗ {trend}</span>
            </div>
            <div className="mt-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
              {label}
            </div>
            <div className="tabular mt-1 text-[28px] font-bold leading-none text-ink-hi">
              {value}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {/* Phân tích xu hướng & rủi ro */}
          <Panel
            title="Phân tích Xu hướng & Rủi ro"
            action={
              <Tabs
                variant="pill"
                tabs={[
                  { id: "week", label: "Tuần này" },
                  { id: "month", label: "Tháng trước" },
                ]}
                active={trendTab}
                onChange={setTrendTab}
              />
            }
          >
            <p className="-mt-1 mb-3 text-2xs text-ink-mid">
              Tổng quan hoạt động rủi ro hệ thống 7 ngày qua.
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                  Mật độ rủi ro toàn cầu
                </div>
                <div className="h-[130px] overflow-hidden rounded-panel border border-line">
                  <RiskDensityMap />
                </div>
              </div>
              <div>
                <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                  Phân bổ theo typology
                </div>
                <div className="space-y-3">
                  {TYPOLOGY_DIST.map((t) => (
                    <div key={t.label}>
                      <div className="mb-1 flex items-center justify-between text-2xs">
                        <span className="text-ink-mid">{t.label}</span>
                        <span className="tabular font-semibold text-ink-hi">{t.pct}%</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded bg-elev">
                        <div
                          className="h-full rounded"
                          style={{ width: `${t.pct}%`, background: t.color }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-2xs">
                  <span className="text-ink-mid">Điểm rủi ro trung bình</span>
                  <span className="tabular text-[18px] font-bold text-ink-hi">68</span>
                </div>
              </div>
            </div>
          </Panel>

          {/* 5 cảnh báo ưu tiên */}
          <Panel
            title="5 Cảnh báo Ưu tiên"
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
            <DataTable
              columns={alertColumns}
              rows={PRIORITY_ALERTS}
              rowKey={(r) => r.id}
              onRowClick={() => navigate("/alerts/ALT-2026-001")}
              dense
            />
          </Panel>
        </div>

        {/* Cột phải */}
        <div className="space-y-3">
          <Panel
            title={
              <span className="inline-flex items-center gap-1.5">
                <Sparkles size={13} className="text-primary" aria-hidden />
                AI Copilot Insights
              </span>
            }
          >
            <div className="-mt-1 mb-2 text-2xs uppercase tracking-wider text-ink-low">
              Phân tích thông minh
            </div>
            <div className="space-y-2.5">
              <div className="rounded-control border border-line bg-elev p-3">
                <div className="flex items-center gap-1.5 text-2xs font-semibold text-primary">
                  <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />
                  Phát hiện Structuring
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                  AI đã phát hiện chuỗi hoạt động gom lẻ tiền mặt qua 3 tài khoản liên kết
                  trong 48h qua. Tổng số tiền: 4,2 tỷ VND.
                </p>
                <div className="mt-2 flex items-center justify-between">
                  <span className="rounded-control bg-risk/10 px-1.5 py-0.5 text-2xs font-medium text-risk">
                    Độ tin cậy: 92%
                  </span>
                  <button
                    type="button"
                    onClick={() => navigate("/alerts/ALT-2026-001")}
                    className="text-2xs font-medium text-primary hover:underline"
                  >
                    Chi tiết →
                  </button>
                </div>
              </div>
              <div className="rounded-control border border-line bg-elev p-3">
                <div className="flex items-center gap-1.5 text-2xs font-semibold text-warn">
                  <span className="h-1.5 w-1.5 rounded-full bg-warn" aria-hidden />
                  Cập nhật Watchlist
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                  Có 12 thực thể mới trùng khớp với danh sách trừng phạt UN vừa cập nhật.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() =>
                pushToast({
                  tone: "info",
                  title: "Đã mở cuộc điều tra mới (mô phỏng)",
                  detail: "Cần con người rà soát trước mọi kết luận.",
                })
              }
              className="mt-3 w-full rounded-control border border-primary/50 bg-primary-soft py-2 text-[13px] font-semibold text-primary hover:border-primary"
            >
              Mở cuộc điều tra mới
            </button>
          </Panel>

          <Panel title="Trạng thái Tuân thủ">
            <div className="space-y-3.5">
              {COMPLIANCE.map(({ label, pct, icon: Icon }) => (
                <div key={label}>
                  <div className="mb-1 flex items-center justify-between text-2xs">
                    <span className="inline-flex items-center gap-1.5 text-ink-mid">
                      <Icon size={12} className="text-primary" aria-hidden />
                      {label}
                    </span>
                    <span className="tabular font-semibold text-ink-hi">{pct}%</span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded bg-elev">
                    <div className="h-full rounded bg-primary" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-line pt-3 text-2xs text-ink-low">
              Lần cuối cập nhật: 10 phút trước
              <button
                type="button"
                aria-label="Làm mới"
                onClick={() => pushToast({ tone: "success", title: "Đã làm mới trạng thái tuân thủ" })}
                className="rounded p-1 hover:bg-elev hover:text-ink-hi"
              >
                <RefreshCw size={12} />
              </button>
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
