import { Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api/client";
import type { ApiMySar } from "../api/client";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { SarCopilotDrawer } from "../components/copilot/SarCopilotDrawer";
import { CaseId, PriorityBadge } from "../components/copilot/atoms";
import { Column, DataTable, PageShell, Panel } from "../components/ui";

/**
 * Báo cáo của tôi — chuyên viên theo dõi hồ sơ mình đã trình.
 *
 * Trước trang này, nộp hồ sơ xong là mất dấu: không màn hình nào cho biết quản
 * lý đã duyệt chưa, trả lại vì lý do gì, hay vẫn đang chờ. Chuyên viên phải hỏi
 * miệng hoặc mở lại từng hồ sơ một.
 *
 * Thứ quan trọng nhất ở đây là CỘT LÝ DO. Một hồ sơ bị trả lại mà không nói vì
 * sao thì người nhận lại không biết phải sửa gì, và vòng lặp bổ sung bằng chứng
 * chạy thêm một lượt vô ích.
 */

const DECISION_LABEL: Record<string, string> = {
  pending: "Chờ quản lý duyệt",
  approved: "Đã phê duyệt",
  rejected: "Bị từ chối",
  more_info: "Cần bổ sung",
};

const DECISION_TONE: Record<string, string> = {
  pending: "text-warn",
  approved: "text-ok",
  rejected: "text-risk",
  more_info: "text-info",
};

export function MyReportsPage() {
  const navigate = useNavigate();
  const reports = useApi(() => api.mySars(), []);
  const [chatOpen, setChatOpen] = useState(false);

  const rows = reports.data ?? [];
  const counts = useMemo(
    () => ({
      pending: rows.filter((r) => !r.decision || r.decision === "pending").length,
      approved: rows.filter((r) => r.decision === "approved").length,
      back: rows.filter((r) => r.decision === "rejected" || r.decision === "more_info").length,
    }),
    [rows],
  );

  const columns: Column<ApiMySar>[] = [
    {
      key: "case",
      header: "Hồ sơ",
      render: (r) => (
        <span className="group/case">
          <CaseId id={r.case_id} />
        </span>
      ),
    },
    {
      key: "risk",
      header: "Rủi ro",
      numeric: true,
      sortValue: (r) => r.risk_score,
      render: (r) => <span className="tabular font-semibold text-ink-hi">{Math.round(r.risk_score)}</span>,
    },
    { key: "priority", header: "Ưu tiên", render: (r) => <PriorityBadge priority={r.priority} /> },
    {
      key: "submitted",
      header: "Đã trình lúc",
      sortValue: (r) => r.submitted_at ?? "",
      render: (r) => <span className="tabular text-ink-mid">{formatDateTime(r.submitted_at)}</span>,
    },
    {
      key: "decision",
      header: "Kết quả",
      render: (r) => {
        const key = r.decision ?? "pending";
        return (
          <span className="block">
            <span className={DECISION_TONE[key] ?? "text-ink-mid"}>
              {DECISION_LABEL[key] ?? r.status}
            </span>
            {r.decided_at && (
              <span className="block text-meta text-ink-dim">
                {formatDateTime(r.decided_at)}
                {r.decided_by_name && ` · ${r.decided_by_name}`}
              </span>
            )}
          </span>
        );
      },
    },
    {
      // Lý do trả lại — cột đáng giá nhất của trang này.
      key: "reason",
      header: "Ý kiến của quản lý",
      render: (r) =>
        r.reason ? (
          <span className="truncate-2 text-ink-mid" title={r.reason}>
            {r.reason}
          </span>
        ) : (
          <span className="text-ink-dim">—</span>
        ),
    },
  ];

  return (
    <PageShell
      title="Báo cáo của tôi"
      subtitle="Hồ sơ nghi vấn bạn đã trình và quyết định của quản lý."
      actions={
        <button
          type="button"
          onClick={() => setChatOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
        >
          <Sparkles size={13} aria-hidden />
          Trợ lý AI
        </button>
      }
    >
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Chờ quản lý duyệt", value: counts.pending, tone: "text-warn" },
            { label: "Đã phê duyệt", value: counts.approved, tone: "text-ok" },
            { label: "Cần bổ sung / bị từ chối", value: counts.back, tone: "text-risk" },
          ].map((k) => (
            <div key={k.label} className="rounded-panel border border-line bg-panel px-3.5 py-2.5">
              <div className="text-meta uppercase tracking-wider text-ink-low">{k.label}</div>
              <div className={`tabular mt-0.5 text-h2 font-bold ${k.tone}`}>{k.value}</div>
            </div>
          ))}
        </div>

        <Panel title="Hồ sơ đã trình" padded={false}>
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.sar_id}
            onRowClick={(r) => navigate(`/sar/${r.sar_id}/edit`)}
            loading={reports.loading && !reports.data}
            dense
            minWidth={820}
            emptyTitle="Bạn chưa trình hồ sơ nào"
            emptyDetail="Hồ sơ nghi vấn bạn gửi lên quản lý sẽ hiện ở đây kèm kết quả phê duyệt."
          />
        </Panel>
      </div>

      <SarCopilotDrawer open={chatOpen} onClose={() => setChatOpen(false)} onExecuted={() => reports.reload()} />
    </PageShell>
  );
}
