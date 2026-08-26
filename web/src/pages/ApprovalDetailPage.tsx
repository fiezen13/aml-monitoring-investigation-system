import { Building2, CheckCircle2, FileDown, Network, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";

import { PageShell } from "../components/ui";
import { StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { ReasonModal } from "../components/common/ReasonModal";
import { Tooltip } from "../components/common/Tooltip";
import { Breadcrumb } from "../components/layout/Breadcrumb";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";

/**
 * Chi tiết phê duyệt SAR — khớp screenshot "Chi tiết Phê duyệt SAR".
 * Quy tắc: người gửi không được tự phê duyệt; Xuất hồ sơ chỉ mở khi APPROVED.
 */
export function ApprovalDetailPage() {
  const { sarId } = useParams();
  const { currentUser, pushToast } = useApp();
  const sarQuery = useApi(() => api.sar(sarId ?? ""), [sarId]);
  const [approveOpen, setApproveOpen] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);

  if (!sarQuery.data) {
    return <div className="p-6 text-body text-ink-mid">{sarQuery.error ?? "Đang tải hồ sơ SAR..."}</div>;
  }
  const sar = sarQuery.data;
  const detail = {
    sar_id: sar.sar_id,
    suspicionType: sar.suspicionType,
    subject: {
      name: sar.subjectName,
      taxCode: `Mã KH: ${sar.subject.customerId} · ${sar.subject.accountKey}`,
      internalRating: ({ high: "CAO", medium: "TRUNG BÌNH", low: "THẤP" } as Record<string, string>)[sar.subject.riskRating?.toLowerCase()] ?? sar.subject.riskRating,
      establishedFor: new Date(sar.subject.onboardingDate).toLocaleDateString("vi-VN"),
      previousSars: sar.case_id,
    },
    behaviourSummary: sar.behaviourSummary,
    transactions: sar.relatedTransactions,
    networkConfidence: sar.networkConfidence,
    networkNote: `${sar.evidence.length} bằng chứng và ${sar.relatedTransactions.length} giao dịch liên quan được truy xuất từ hệ thống.`,
    history: sar.history,
  };

  const status = sar.status;

  const isApproved = status === "APPROVED";
  const isPending = status === "PENDING_REVIEW";
  const isSelfApproval =
    currentUser != null && currentUser.name === sar.submittedBy;
  const isManager = currentUser?.role === "manager";
  const canApprove = isPending && !isSelfApproval && isManager;

  const approveBlockedReason = !isPending
    ? "Báo cáo không ở trạng thái chờ phê duyệt"
    : isSelfApproval
      ? "Người gửi không được tự phê duyệt SAR do chính mình gửi"
      : !isManager
        ? "Chỉ vai trò Quản lý mới có quyền phê duyệt SAR"
        : "";

  return (
    <PageShell>
      <Breadcrumb
        items={[
          { label: "Phê duyệt SAR", to: "/approvals" },
          { label: "Chi tiết phê duyệt" },
        ]}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="tabular text-h2 font-bold text-ink-hi">{detail.sar_id}</h1>
        {isApproved ? (
          <StatusBadge tone="ok" label="ĐÃ PHÊ DUYỆT" />
        ) : status === "REJECTED" ? (
          <StatusBadge tone="risk" label="ĐÃ TỪ CHỐI" />
        ) : (
          <StatusBadge tone="warn" label="ĐANG CHỜ RÀ SOÁT" />
        )}
        <div className="ml-auto flex items-center gap-2">
          {isPending && (
            <Tooltip content={canApprove ? "Phê duyệt kèm lý do bắt buộc" : approveBlockedReason}>
              <button
                type="button"
                disabled={!canApprove}
                onClick={() => setApproveOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-body font-semibold text-app hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
              >
                <CheckCircle2 size={14} aria-hidden />
                Phê duyệt
              </button>
            </Tooltip>
          )}
          {isPending && canApprove && (
            <button
              type="button"
              onClick={() => setRejectOpen(true)}
              className="rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi hover:border-risk/50 hover:text-risk"
            >
              Từ chối
            </button>
          )}
          <Tooltip
            content={
              isApproved
                ? "Xuất hồ sơ SAR đã phê duyệt và ghi audit"
                : "Chỉ xuất được hồ sơ khi SAR ở trạng thái đã phê duyệt — không có đường tắt nào bỏ qua người phê duyệt"
            }
          >
            <button
              type="button"
              disabled={!isApproved}
              onClick={async () => {
                try {
                  const result = await api.exportSar(sar.sar_id);
                  await sarQuery.reload();
                  pushToast({ tone: "success", title: `Đã tải ${result.filename}`, detail: "PDF hồ sơ đã tải về; vụ việc chuyển XuatHoSo và audit đã ghi." });
                } catch (cause) {
                  pushToast({ tone: "error", title: "Không xuất được hồ sơ", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
                }
              }}
              className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileDown size={14} aria-hidden />
              Xuất hồ sơ
            </button>
          </Tooltip>
        </div>
      </div>

      {isSelfApproval && isPending && (
        <div className="mb-3 flex items-center gap-2 rounded-panel border border-warn/40 bg-warn/10 px-3 py-2.5 text-body text-warn">
          <ShieldCheck size={14} aria-hidden />
          Bạn là người gửi báo cáo này — theo nguyên tắc bốn mắt, hãy chuyển sang tài khoản
          MLRO (Đàm Minh Tuấn) qua menu tài khoản để phê duyệt.
        </div>
      )}

      <div className="grid gap-3 xl:grid-cols-[1fr_300px]">
        {/* Nội dung báo cáo */}
        <div className="space-y-3">
          <Panel
            title="Nội dung Báo cáo SAR"
            action={<StatusBadge tone="ok" label="KIỂM CHỨNG ĐẠT" />}
          >
            <div className="grid grid-cols-[1fr_auto] gap-4">
              <div>
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-low">
                  Loại nghi vấn
                </div>
                <p className="mt-1 text-body text-ink-hi">{detail.suspicionType}</p>
              </div>
              <div>
                <div className="text-2xs font-semibold uppercase tracking-wider text-ink-low">
                  Mức độ rủi ro
                </div>
                <div className="mt-1">
                  <StatusBadge tone="risk" label="CAO" />
                </div>
              </div>
            </div>
            <div className="mt-4">
              <div className="text-2xs font-semibold uppercase tracking-wider text-ink-low">
                Tóm tắt hành vi
              </div>
              <p className="mt-1.5 rounded-control border border-line bg-elev p-3 text-body leading-relaxed text-ink-mid">
                {detail.behaviourSummary}
              </p>
            </div>
            <div className="mt-4">
              <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-low">
                Danh sách giao dịch liên quan
              </div>
              <div className="overflow-x-auto rounded-control border border-line">
                <table className="w-full min-w-[520px] text-left">
                  <thead>
                    <tr className="border-b border-line bg-elev">
                      {["Mã giao dịch", "Thời gian", "Số tiền", "Địa điểm"].map((h) => (
                        <th
                          key={h}
                          className="px-3 py-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {detail.transactions.map((t) => (
                      <tr key={t.transaction_id} className="border-b border-line/60 last:border-0">
                        <td className="tabular px-3 py-2 text-body font-medium text-info">
                          {t.transaction_id}
                        </td>
                        <td className="tabular px-3 py-2 text-body text-ink-mid">{t.time}</td>
                        <td className="tabular px-3 py-2 text-body text-ink-hi">{t.amount}</td>
                        <td className="px-3 py-2 text-body text-ink-mid">{t.location}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </Panel>
        </div>

        {/* Cột phải */}
        <div className="space-y-3">
          <Panel title="Đối tượng tình nghi">
            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-panel bg-elev text-ink-mid">
                <Building2 size={18} aria-hidden />
              </span>
              <div>
                <div className="text-body font-bold text-ink-hi">{detail.subject.name}</div>
                <div className="tabular text-2xs text-ink-low">{detail.subject.taxCode}</div>
              </div>
            </div>
            <dl className="mt-3 space-y-2.5 border-t border-line pt-3 text-2xs">
              <div className="flex items-center justify-between">
                <dt className="text-ink-low">Xếp hạng nội bộ</dt>
                <dd>
                  <StatusBadge tone="risk" label={detail.subject.internalRating} />
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-ink-low">Thời gian thiết lập</dt>
                <dd className="tabular font-medium text-ink-hi">
                  {detail.subject.establishedFor}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-ink-low">Lượt SAR trước đó</dt>
                <dd className="tabular font-medium text-ink-hi">{detail.subject.previousSars}</dd>
              </div>
            </dl>
          </Panel>

          <Panel
            title={
              <span className="inline-flex items-center gap-1.5">
                <Network size={13} aria-hidden />
                Mạng lưới liên kết (AI)
              </span>
            }
          >
            <div className="flex flex-col items-center rounded-control border border-line bg-elev py-5">
              <span className="tabular text-h1 font-bold text-ok">
                {detail.networkConfidence}%
              </span>
              <span className="text-2xs uppercase tracking-wider text-ink-low">
                Độ tin cậy
              </span>
            </div>
            <p className="mt-2.5 text-2xs leading-relaxed text-ink-mid">{detail.networkNote}</p>
            <p className="mt-1.5 text-2xs text-ink-low">Nguồn: Công cụ phân tích mạng lưới</p>
          </Panel>

          <Panel title="Lịch sử xử lý">
            <ol className="relative ml-1.5 space-y-3.5 border-l border-line pl-4">
              {detail.history.map((h) => (
                <li key={h.time} className="relative">
                  <span
                    className="absolute -left-[21px] top-1 h-2 w-2 rounded-full border-2 border-panel bg-primary"
                    aria-hidden
                  />
                  <div className="text-2xs font-semibold text-ink-hi">{h.text}</div>
                  <div className="tabular text-2xs text-ink-low">
                    {h.time} · {h.actor}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </div>
      </div>

      <ReasonModal
        open={approveOpen}
        title={`Phê duyệt ${detail.sar_id}`}
        description="Phê duyệt ghi một lần và không sửa lại được. Lý do là bắt buộc và được lưu bất biến vào audit trail."
        confirmLabel="Xác nhận phê duyệt"
        minLength={30}
        onClose={() => setApproveOpen(false)}
        onConfirm={async (reason) => {
          try {
            if (!sar.approval) throw new Error("Hồ sơ chưa có yêu cầu phê duyệt");
            await api.decideApproval(sar.approval.approval_id, "approved", reason);
            await sarQuery.reload();
            setApproveOpen(false);
            pushToast({ tone: "success", title: `Đã phê duyệt ${detail.sar_id}`, detail: "Quyết định đã được lưu và ghi nhật ký." });
          } catch (cause) {
            pushToast({ tone: "error", title: "Phê duyệt thất bại", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
          }
        }}
      />
      <ReasonModal
        open={rejectOpen}
        title={`Từ chối ${detail.sar_id}`}
        description="Báo cáo sẽ trả về người gửi kèm lý do bắt buộc — ghi bất biến vào audit trail."
        confirmLabel="Từ chối báo cáo"
        minLength={30}
        onClose={() => setRejectOpen(false)}
        onConfirm={async (reason) => {
          try {
            if (!sar.approval) throw new Error("Hồ sơ chưa có yêu cầu phê duyệt");
            await api.decideApproval(sar.approval.approval_id, "rejected", reason);
            await sarQuery.reload();
            setRejectOpen(false);
            pushToast({ tone: "info", title: `Đã từ chối ${detail.sar_id}`, detail: "Hồ sơ đã chuyển sang Điều tra bổ sung." });
          } catch (cause) {
            pushToast({ tone: "error", title: "Từ chối thất bại", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
          }
        }}
      />
    </PageShell>
  );
}
