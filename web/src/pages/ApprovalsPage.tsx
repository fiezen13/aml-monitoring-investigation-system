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

import { axisProps } from "../design/adapters/rechartsTheme";
import { toneColor } from "../design/semantic";
import { PageShell } from "../components/ui";
import { TEXT } from "../design/typography";
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
  // Đề nghị ĐÓNG vụ: chuyên viên kết luận không đáng ngờ nhưng vụ vượt ngưỡng
  // rủi ro nên phải qua quản lý. Không nằm trong `sars()` vì không có bản nháp.
  const closeReqs = useApi(() => api.closeRequests(), []);

  // Trợ lý AI thật (Gemini) hỏi–đáp về hàng đợi SAR — chỉ tư vấn, không tự quyết.
  const [chatOpen, setChatOpen] = useState(false);
  const [chatMsgs, setChatMsgs] = useState<{ role: "user" | "assistant"; text: string }[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatSending, setChatSending] = useState(false);

  async function sendChat() {
    const q = chatInput.trim();
    if (!q || chatSending) return;
    const history = chatMsgs.slice(-6);
    setChatMsgs((m) => [...m, { role: "user", text: q }]);
    setChatInput("");
    setChatSending(true);
    try {
      const res = await api.sarAiChat(q, history);
      setChatMsgs((m) => [...m, { role: "assistant", text: res.answer }]);
    } catch {
      setChatMsgs((m) => [...m, { role: "assistant", text: "Không gọi được trợ lý AI. Thử lại sau." }]);
    } finally {
      setChatSending(false);
    }
  }

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
      header: "Mã hồ sơ",
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

  const pendingCloses = closeReqs.data ?? [];
  const [decidingId, setDecidingId] = useState<string | null>(null);

  async function decideClose(approvalId: string, decision: "approved" | "rejected") {
    setDecidingId(approvalId);
    try {
      await api.decideApproval(
        approvalId,
        decision,
        decision === "approved"
          ? "Quản lý duyệt đề nghị đóng vụ, không lập báo cáo."
          : "Quản lý không duyệt đề nghị đóng; trả lại để điều tra bổ sung.",
      );
      pushToast({
        tone: "success",
        title: decision === "approved" ? "Đã đóng vụ việc" : "Đã trả lại cho chuyên viên",
      });
      closeReqs.reload();
    } catch (error) {
      pushToast({ tone: "error", title: error instanceof Error ? error.message : "Không lưu được quyết định" });
    } finally {
      setDecidingId(null);
    }
  }

  return (
    <PageShell>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className={TEXT.h2}>Hàng đợi phê duyệt</h2>
          <p className="mt-1 text-body text-ink-soft">
            Thẩm định hồ sơ nghi vấn do chuyên viên nộp, và chốt các đề nghị đóng vụ.
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

      {/* ĐỀ NGHỊ ĐÓNG VỤ — hàng đợi thứ hai của quản lý.
          Chuyên viên kết luận "không đáng ngờ" trên một vụ VƯỢT ngưỡng rủi ro
          thì không tự đóng được; đề nghị nằm ở đây chờ chốt. Dưới ngưỡng thì họ
          đã đóng thẳng và vụ không bao giờ xuất hiện ở màn hình này. */}
      {pendingCloses.length > 0 && (
        <Panel title={`Đề nghị đóng vụ · ${pendingCloses.length}`}>
          <p className="mb-2 text-2xs text-ink-mid">
            Chuyên viên kết luận không đáng ngờ; vụ vượt ngưỡng rủi ro nên cần quản lý chốt.
          </p>
          <div className="space-y-2">
            {pendingCloses.map((r) => (
              <div
                key={r.approval_id}
                className="rounded-control border border-line bg-elev px-3 py-2.5 text-2xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => navigate(`/cases/${r.case_id}`)}
                    className="font-semibold text-ink-hi hover:underline"
                  >
                    {r.case_id}
                  </button>
                  <span className="tabular text-ink-mid">
                    điểm rủi ro <span className="font-semibold text-ink-hi">{Math.round(Number(r.risk_score))}</span>
                  </span>
                </div>
                {r.analyst_reason && (
                  <p className="mt-1.5 text-ink-mid">Lý do chuyên viên nêu: {r.analyst_reason}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={decidingId === r.approval_id}
                    onClick={() => decideClose(r.approval_id, "approved")}
                    className="rounded-control bg-primary px-3 py-1.5 font-semibold text-app disabled:opacity-50"
                  >
                    Duyệt đóng vụ
                  </button>
                  <button
                    type="button"
                    disabled={decidingId === r.approval_id}
                    onClick={() => decideClose(r.approval_id, "rejected")}
                    className="rounded-control border border-line px-3 py-1.5 font-semibold text-ink-mid disabled:opacity-50"
                  >
                    Không duyệt — trả lại điều tra
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* KPI */}
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {[
          {
            label: "Tổng SAR chờ duyệt",
            value: String(pendingCount),
            note: "Đang chờ duyệt",
            noteTone: "text-ok",
            icon: ClipboardList,
          },
          {
            label: "Ưu tiên cao",
            value: String(rows.filter((row) => row.flagged).length),
            note: "Theo điểm rủi ro",
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
            <div className="tabular mt-1 text-h1 font-bold leading-none text-ink-hi">
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
            Hiển thị {rows.length} bản ghi
          </span>
        }
      >
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(a) => a.sar_id}
          onRowClick={(a) => navigate(`/approvals/${a.sar_id}`)}
          loading={sars.loading}
          error={sars.error}
          onRetry={sars.reload}
          emptyTitle="Chưa có SAR chờ xử lý"
          emptyDetail="Cảnh báo mô hình không tự trở thành SAR; chuyên viên phải mở case, lập báo cáo và gửi phê duyệt."
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
                  tick={axisProps.tick}
                />
                <Bar dataKey="feedback" stackId="a" fill={toneColor("risk")} isAnimationActive={false} />
                <Bar
                  dataKey="approved"
                  stackId="a"
                  fill={toneColor("primary")}
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
              Tóm tắt AI: Hàng đợi SAR
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
                Số liệu lấy trực tiếp từ dữ liệu thật.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="mt-3 inline-flex w-full items-center justify-center gap-1.5 rounded-control bg-primary py-2 text-body font-semibold text-app hover:bg-primary-hover"
          >
            <Sparkles size={13} aria-hidden />
            Hỏi trợ lý AI về hàng đợi
          </button>
        </Panel>
      </div>

      {chatOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-3 sm:items-center"
          role="dialog"
          aria-modal="true"
          onClick={() => setChatOpen(false)}
        >
          <div
            className="flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-panel border border-line bg-panel shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2 border-b border-line px-4 py-3">
              <Sparkles size={15} className="text-primary" aria-hidden />
              <span className="text-body-lg font-semibold text-ink-hi">Trợ lý AI · Hàng đợi SAR</span>
              <button
                type="button"
                onClick={() => setChatOpen(false)}
                className="ml-auto text-ink-mid hover:text-ink-hi"
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 space-y-2.5 overflow-y-auto px-4 py-3 text-2xs">
              {chatMsgs.length === 0 && (
                <div className="rounded-control border border-line bg-elev p-3 text-ink-mid">
                  Hỏi về hàng đợi phê duyệt SAR — ví dụ: “hồ sơ nào rủi ro cao nhất và vì sao”, “còn bao nhiêu vụ chờ
                  quyết định”, “hồ sơ nào còn câu chưa dẫn bằng chứng”. Trợ lý dựa trên dữ liệu thật, chỉ tư vấn — quyết
                  định duyệt/từ chối vẫn là của bạn.
                </div>
              )}
              {chatMsgs.map((m, i) => (
                <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
                  <div
                    className={`max-w-[85%] whitespace-pre-wrap rounded-control px-3 py-2 leading-relaxed ${
                      m.role === "user" ? "bg-primary text-app" : "border border-line bg-elev text-ink-hi"
                    }`}
                  >
                    {m.text}
                  </div>
                </div>
              ))}
              {chatSending && <div className="text-ink-low">Trợ lý đang trả lời…</div>}
            </div>

            <div className="flex items-end gap-2 border-t border-line px-3 py-3">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void sendChat();
                  }
                }}
                rows={2}
                placeholder="Nhập câu hỏi… (Enter để gửi)"
                className="min-h-[40px] flex-1 resize-none rounded-control border border-line bg-elev px-3 py-2 text-2xs text-ink-hi focus:border-line-emphasis focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void sendChat()}
                disabled={chatSending || !chatInput.trim()}
                className="rounded-control bg-primary px-4 py-2 text-2xs font-semibold text-app hover:bg-primary-hover disabled:opacity-50"
              >
                Gửi
              </button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  );
}
