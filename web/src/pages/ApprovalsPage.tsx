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
import { useApp } from "../context/AppContext";
import { APPROVALS } from "../data/mockSar";
import type { Approval } from "../types";

const WEEK_DATA = [
  { day: "Mon", approved: 8, feedback: 3 },
  { day: "Tue", approved: 12, feedback: 4 },
  { day: "Wed", approved: 10, feedback: 3 },
  { day: "Thu", approved: 14, feedback: 5 },
  { day: "Fri", approved: 11, feedback: 4 },
  { day: "Sat", approved: 4, feedback: 2 },
  { day: "Sun", approved: 3, feedback: 1 },
];

const SLA_BAR: Record<Approval["slaTone"], string> = {
  risk: "bg-risk",
  warn: "bg-warn",
  info: "bg-info",
  ok: "bg-ok",
};

/** Hàng đợi phê duyệt SAR — góc nhìn MLRO, khớp screenshot cùng tên. */
export function ApprovalsPage() {
  const navigate = useNavigate();
  const { sarStatus, sarSubmittedBy, pushToast } = useApp();
  const [listTab, setListTab] = useState("all");
  const [page, setPage] = useState(1);

  /** SAR-2026-007 xuất hiện trong hàng đợi sau khi được gửi từ màn hình soạn thảo. */
  const rows = useMemo(() => {
    const base = [...APPROVALS];
    if (sarStatus === "PENDING_REVIEW" || sarStatus === "APPROVED" || sarStatus === "REJECTED") {
      base.unshift({
        sar_id: "SAR-2026-007",
        sender: sarSubmittedBy,
        senderRole: "Compliance Officer",
        status:
          sarStatus === "PENDING_REVIEW"
            ? "pending"
            : sarStatus === "APPROVED"
              ? "approved"
              : "rejected",
        statusLabel:
          sarStatus === "PENDING_REVIEW"
            ? "Chờ phê duyệt"
            : sarStatus === "APPROVED"
              ? "Đã phê duyệt"
              : "Bị từ chối",
        sla: "Còn 7h 40m",
        slaPct: 68,
        slaTone: "info",
        validation: "100% Passed",
        validationTone: "ok",
        flagged: true,
      });
    }
    if (listTab === "pending") return base.filter((a) => a.status === "pending" || a.status === "needs_info");
    if (listTab === "done") return base.filter((a) => a.status === "approved" || a.status === "rejected");
    return base;
  }, [sarStatus, sarSubmittedBy, listTab]);

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
      header: "Validation Status",
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
      render: () => <span className="font-medium text-primary">Xem chi tiết</span>,
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
            onClick={() => pushToast({ tone: "success", title: "Đã xuất báo cáo hàng đợi (mô phỏng)" })}
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
            value: "42",
            note: "+12% vs tuần trước",
            noteTone: "text-ok",
            icon: ClipboardList,
          },
          {
            label: "Ưu tiên cao",
            value: "15",
            note: "8 quá hạn SLA",
            noteTone: "text-risk",
            icon: OctagonAlert,
          },
          {
            label: "Cần bổ sung",
            value: "09",
            note: "4 đã phản hồi",
            noteTone: "text-warn",
            icon: MessageSquareWarning,
          },
          {
            label: "Đã duyệt hôm nay",
            value: "18",
            note: "3.2m avg. time",
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
            Hiển thị {rows.length} trong số 42 bản ghi
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
          <Pagination page={page} pageCount={5} onChange={setPage} summary="" />
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
              <BarChart data={WEEK_DATA} barSize={14}>
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
                Có 3 báo cáo SAR đang tiếp cận ngưỡng trễ hạn SLA (&lt; 1h). Ưu tiên phê
                duyệt mã SAR-2026-008 ngay lập tức.
              </p>
            </div>
            <div className="rounded-control border border-line bg-elev p-3">
              <div className="text-2xs font-semibold uppercase tracking-wide text-info">
                Gợi ý thẩm định
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                Hệ thống phát hiện sự trùng lặp trong lý do trì hoãn của SAR-2026-009 và
                SAR-2026-011. Khuyến nghị kiểm tra chéo người gửi.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => pushToast({ tone: "info", title: "AI Chat chi tiết (mô phỏng)" })}
            className="mt-3 w-full rounded-control border border-line py-2 text-[13px] font-medium text-ink-hi hover:border-primary/50"
          >
            Mở AI Chat chi tiết
          </button>
        </Panel>
      </div>
    </div>
  );
}
