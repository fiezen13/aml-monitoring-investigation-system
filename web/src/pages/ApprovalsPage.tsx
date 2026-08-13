import {
  CheckCheck,
  ClipboardList,
  Download,
  Filter,
  Flag,
  MessageSquareWarning,
  OctagonAlert,
  Sparkles,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Bar,
  BarChart,
  ResponsiveContainer,
  XAxis,
} from "recharts";

import { FailBadge, StatusBadge } from "../components/common/Badges";
import { Pagination } from "../components/common/Pagination";
import { Panel } from "../components/common/Panel";
import { Tabs } from "../components/common/Tabs";
import { DataTable, type Column } from "../components/tables/DataTable";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";
import type { Approval } from "../types";

const SLA_BAR: Record<Approval["slaTone"], string> = {
  risk: "bg-risk",
  warn: "bg-warn",
  info: "bg-info",
  ok: "bg-ok",
};

/** Hàng đợi phê duyệt SAR — góc nhìn MLRO, khớp screenshot cùng tên. */
export function ApprovalsPage() {
  const navigate = useNavigate();
  const { pushToast } = useApp();
  const [listTab, setListTab] = useState("all");
  const [page, setPage] = useState(1);
  const sars = useApi(() => api.sars(), []);

  const rows = useMemo(() => {
    const base: Approval[] = (sars.data ?? []).map((sar) => {
      const status = sar.status === "PENDING_REVIEW" ? "pending" : sar.status === "NEEDS_INFO" ? "needs_info" : sar.status === "APPROVED" ? "approved" : sar.status === "REJECTED" ? "rejected" : "needs_info";
      return {
        sar_id: sar.sar_id,
        sender: sar.submittedBy,
        senderRole: sar.submittedByRole,
        status,
        statusLabel: status === "pending" ? "Chờ phê duyệt" : status === "needs_info" ? "Đang soạn/Cần bổ sung" : status === "approved" ? "Đã phê duyệt" : "Bị từ chối",
        sla: sar.approval?.requested_at ? new Date(sar.approval.requested_at).toLocaleString("vi-VN") : "Chưa gửi",
        slaPct: status === "pending" ? 70 : 100,
        slaTone: status === "pending" ? "warn" : status === "approved" ? "ok" : "info",
        validation: sar.validationIssues.length === 0 ? "Bằng chứng hợp lệ" : `${sar.validationIssues.length} lỗi`,
        validationTone: sar.validationIssues.length === 0 ? "ok" : "risk",
        flagged: sar.riskLevel === "CAO",
      };
    });
    if (listTab === "pending") return base.filter((a) => a.status === "pending" || a.status === "needs_info");
    if (listTab === "done") return base.filter((a) => a.status === "approved" || a.status === "rejected");
    return base;
  }, [sars.data, listTab]);

  const pendingCount = rows.filter((row) => row.status === "pending").length;
  const approvedCount = rows.filter((row) => row.status === "approved").length;
  const feedbackCount = rows.filter((row) => row.status === "needs_info" || row.status === "rejected").length;
  const weekData = [{ day: "Hiện tại", approved: approvedCount, feedback: feedbackCount }];

  const columns: Column<Approval>[] = [
    {
      key: "id",
      header: "Case ID",
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <Flag
            size={13}
            aria-hidden
            className={a.flagged ? "text-risk" : "text-ink-low"}
          />
          <span className="tabular font-semibold text-ink-hi">{a.sar_id}</span>
        </span>
      ),
    },
    {
      key: "sender",
      header: "Người gửi",
      render: (a) => (
        <span className="inline-flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-elev text-2xs font-bold text-primary">
            {a.sender
              .split(" ")
              .slice(-2)
              .map((w) => w[0])
              .join("")}
          </span>
          <span>
            {a.sender} <span className="text-ink-low">- {a.senderRole}</span>
          </span>
        </span>
      ),
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (a) => (
        <StatusBadge
          tone={
            a.status === "pending"
              ? "risk"
              : a.status === "needs_info"
                ? "warn"
                : a.status === "approved"
                  ? "ok"
                  : "muted"
          }
          label={a.statusLabel}
        />
      ),
    },
    {
      key: "sla",
      header: "SLA",
      render: (a) => (
        <div className="min-w-[110px]">
          <div
            className={`tabular text-2xs font-medium ${
              a.slaTone === "risk" ? "text-risk" : "text-ink-mid"
            }`}
          >
            {a.sla}
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded bg-elev">
            <div className={`h-full rounded ${SLA_BAR[a.slaTone]}`} style={{ width: `${a.slaPct}%` }} />
          </div>
        </div>
      ),
    },
    {
      key: "validation",
      header: "Trạng thái kiểm chứng",
      render: (a) =>
        a.validationTone === "ok" ? (
          <StatusBadge tone="ok" label={a.validation} />
        ) : a.validationTone === "warn" ? (
          <StatusBadge tone="warn" label={a.validation} />
        ) : (
          <FailBadge label={a.validation} />
        ),
    },
    {
      key: "action",
      header: "Thao tác",
      render: () => <span className="font-medium text-info-soft">Xem chi tiết</span>,
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-[20px] font-bold text-ink-hi">Hàng đợi phê duyệt SAR</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">
            Quản lý và thẩm định các báo cáo giao dịch đáng ngờ trong hệ thống FIN-07.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi"
          >
            <Filter size={12} aria-hidden />
            Bộ lọc
          </button>
          <button
            type="button"
            onClick={() => {
              const content = ["sar_id,status,submitted_by", ...rows.map((item) => `${item.sar_id},${item.status},${item.sender}`)].join("\n");
              const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }));
              const link = document.createElement("a");
              link.href = url;
              link.download = "sar-approval-queue.csv";
              link.click();
              URL.revokeObjectURL(url);
              pushToast({ tone: "success", title: "Đã xuất hàng đợi hiện tại" });
            }}
            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-2.5 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover"
          >
            <Download size={12} aria-hidden />
            Xuất báo cáo
          </button>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          {
            label: "Tổng SAR chờ duyệt",
            value: String(pendingCount),
            note: "Từ PostgreSQL",
            noteTone: "text-ok",
            icon: ClipboardList,
          },
          {
            label: "Ưu tiên cao",
            value: String(rows.filter((row) => row.flagged).length),
            note: "Theo risk score",
            noteTone: "text-risk",
            icon: OctagonAlert,
          },
          {
            label: "Cần bổ sung",
            value: String(feedbackCount),
            note: "Cần xử lý",
            noteTone: "text-warn",
            icon: MessageSquareWarning,
          },
          {
            label: "Đã duyệt hôm nay",
            value: String(approvedCount),
            note: "Trong dữ liệu hiện tại",
            noteTone: "text-ink-mid",
            icon: CheckCheck,
          },
        ].map(({ label, value, note, noteTone, icon: Icon }) => (
          <div key={label} className="rounded-panel border border-line bg-panel p-4">
            <div className="flex items-center justify-between">
              <Icon size={15} className="text-primary" aria-hidden />
              <span className={`text-2xs font-medium ${noteTone}`}>{note}</span>
            </div>
            <div className="mt-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
              {label}
            </div>
            <div className="tabular mt-1 text-[26px] font-bold leading-none text-ink-hi">
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* Bảng SAR */}
      <Panel
        padded={false}
        title={
          <div className="flex items-center gap-3">
            <span>Danh sách báo cáo SAR</span>
            <Tabs
              variant="pill"
              tabs={[
                { id: "all", label: "Tất cả" },
                { id: "pending", label: "Chờ xử lý" },
                { id: "done", label: "Đã hoàn tất" },
              ]}
              active={listTab}
              onChange={setListTab}
            />
          </div>
        }
        action={
          <span className="tabular text-2xs text-ink-low">
            Hiển thị {rows.length} bản ghi từ DB
          </span>
        }
      >
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(a) => a.sar_id}
          onRowClick={(a) => navigate(`/approvals/${a.sar_id}`)}
        />
        <div className="border-t border-line px-2">
          <Pagination page={page} pageCount={1} onChange={setPage} summary="" />
        </div>
      </Panel>

      {/* Hàng dưới */}
      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <Panel title="Xu hướng xử lý SAR (Tuần qua)">
          <div className="mb-2 flex items-center gap-4 text-2xs text-ink-mid">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-primary" aria-hidden />
              Đã duyệt
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-risk" aria-hidden />
              Phản hồi
            </span>
          </div>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={weekData} barSize={14}>
                <XAxis
                  dataKey="day"
                  axisLine={false}
                  tickLine={false}
                  tick={{ fill: "#64748B", fontSize: 10 }}
                />
                <Bar dataKey="feedback" stackId="a" fill="#EF4444" isAnimationActive={false} />
                <Bar
                  dataKey="approved"
                  stackId="a"
                  fill="#00B2A9"
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel
          title={
            <span className="inline-flex items-center gap-1.5">
              <Sparkles size={13} className="text-primary" aria-hidden />
              AI Summary: SAR Queue
            </span>
          }
        >
          <div className="space-y-2.5">
            <div className="rounded-control border border-line bg-elev p-3">
              <div className="text-2xs font-semibold uppercase tracking-wide text-warn">
                Cảnh báo SLA
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                Có {pendingCount} báo cáo đang chờ quyết định và {rows.filter((row) => row.flagged).length} hồ sơ rủi ro cao.
              </p>
            </div>
            <div className="rounded-control border border-line bg-elev p-3">
              <div className="text-2xs font-semibold uppercase tracking-wide text-info">
                Gợi ý thẩm định
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                Số liệu tổng hợp trực tiếp từ bảng sar_draft và approval; không dùng dữ liệu mẫu trong trình duyệt.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => pushToast({ tone: "info", title: "AI Chat chưa bật vì môi trường chưa cấu hình model" })}
            className="mt-3 w-full rounded-control border border-line py-2 text-[13px] font-medium text-ink-hi hover:border-line-emphasis"
          >
            Mở AI Chat chi tiết
          </button>
        </Panel>
      </div>
    </div>
  );
}
