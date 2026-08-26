import { FileUp, Play, Send } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PageShell } from "../components/ui";
import { StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { ReasonModal } from "../components/common/ReasonModal";
import { EmptyState } from "../components/common/States";
import { Tabs } from "../components/common/Tabs";
import { Breadcrumb } from "../components/layout/Breadcrumb";
import { EvidenceDrawer } from "../components/evidence/EvidenceDrawer";
import { SARStatement } from "../components/sar/SARStatement";
import { ValidationPanel } from "../components/sar/ValidationPanel";
import { api } from "../api/client";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";
import { formatCompactVnd } from "../utils/format";

const TABS = [
  { id: "summary", label: "Tóm tắt" },
  { id: "flow", label: "Chi tiết luồng tiền" },
  { id: "customer", label: "Thông tin khách hàng" },
];

/** Rà soát bản nháp SAR — SAR-2026-007, khớp screenshot cùng tên. */
export function SarEditPage() {
  const { sarId } = useParams();
  const navigate = useNavigate();
  const { currentUser, pushToast } = useApp();
  const sarQuery = useApi(() => api.sar(sarId ?? ""), [sarId]);
  const [tab, setTab] = useState("summary");
  const [drawerEvidence, setDrawerEvidence] = useState<string | null>(null);
  const [submitOpen, setSubmitOpen] = useState(false);

  if (!sarQuery.data) {
    return (
      <EmptyState
        title={sarQuery.error ? "Không tìm thấy bản nháp SAR" : "Đang tải SAR"}
        detail={sarQuery.error ?? "Đang tải..."}
      />
    );
  }

  const SAR_DRAFT = sarQuery.data;
  const sarStatus = SAR_DRAFT.status;
  const sarIssues = SAR_DRAFT.validationIssues;
  const inspectorItems = SAR_DRAFT.evidence.slice(0, 6).map((item) => ({
    id: item.id,
    title: item.title,
    tags: item.tags,
    evidence: item.id,
  }));

  const canSubmit = sarStatus === "VALIDATION_PASSED";
  const submitted =
    sarStatus === "PENDING_REVIEW" || sarStatus === "APPROVED" || sarStatus === "REJECTED";

  return (
    <PageShell>
      <Breadcrumb
        items={[
          { label: "Phê duyệt SAR", to: "/approvals" },
          { label: `Bản nháp ${SAR_DRAFT.sar_id}` },
        ]}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-h2 font-bold text-ink-hi">
          Rà soát bản nháp {SAR_DRAFT.sar_id}
        </h1>
        {sarStatus === "DRAFT" && <StatusBadge tone="muted" label="BẢN NHÁP" />}
        {sarStatus === "VALIDATION_FAILED" && (
          <StatusBadge tone="risk" label={`CẦN RÀ SOÁT (${sarIssues.length} lỗi)`} />
        )}
        {sarStatus === "VALIDATION_PASSED" && <StatusBadge tone="ok" label="KIỂM CHỨNG ĐẠT" />}
        {sarStatus === "PENDING_REVIEW" && <StatusBadge tone="warn" label="ĐANG CHỜ PHÊ DUYỆT" />}
        {sarStatus === "APPROVED" && <StatusBadge tone="ok" label="ĐÃ PHÊ DUYỆT" />}
        {sarStatus === "REJECTED" && <StatusBadge tone="risk" label="BỊ TỪ CHỐI" />}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            disabled={submitted}
            onClick={async () => {
              try {
                await api.validateSar(SAR_DRAFT.sar_id);
                await sarQuery.reload();
                pushToast({ tone: "success", title: "Kiểm chứng đạt", detail: "Mọi nhận định đã có bằng chứng; đã ghi nhật ký." });
              } catch (cause) {
                pushToast({ tone: "error", title: "Kiểm chứng thất bại", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
              }
            }}
            className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi hover:border-line-emphasis disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Play size={13} aria-hidden />
            Chạy kiểm chứng
          </button>
          <button
            type="button"
            disabled={!canSubmit}
            title={
              canSubmit
                ? undefined
                : submitted
                  ? "Bản nháp đã được gửi phê duyệt"
                  : "Phải chạy kiểm chứng và xử lý hết lỗi trước khi gửi phê duyệt"
            }
            onClick={() => setSubmitOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-body font-semibold text-app hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Send size={13} aria-hidden />
            Gửi phê duyệt
          </button>
        </div>
      </div>

      <div className="grid gap-3 xl:grid-cols-[1fr_320px]">
        {/* Cột trái */}
        <div className="space-y-3">
          <Panel padded={false}>
            <div className="px-4 pt-3">
              <Tabs tabs={TABS} active={tab} onChange={setTab} variant="pill" />
            </div>

            {tab === "summary" && (
              <div className="space-y-4 p-4">
                <div>
                  <div className="mb-2 text-body-lg font-semibold text-ink-hi">
                    Tóm tắt hành vi nghi vấn
                  </div>
                  <p className="text-body leading-relaxed text-ink-mid">
                    {SAR_DRAFT.behaviourSummary}
                  </p>
                </div>
                <div>
                  <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                    Nhận định kèm bằng chứng (câu thiếu bằng chứng bị chặn khi gửi)
                  </div>
                  <div className="space-y-2">
                    {SAR_DRAFT.statements.map((st) => (
                      <SARStatement
                        key={st.id}
                        statement={st}
                        onOpenEvidence={setDrawerEvidence}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {tab === "flow" && (
              <div className="space-y-4 p-4">
                <div className="text-body-lg font-semibold text-ink-hi">Phân tích luồng tiền</div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-panel border border-line bg-elev p-3.5">
                    <div className="text-2xs uppercase tracking-wide text-ink-low">
                      Nguồn tiền vào
                    </div>
                    <div className="tabular mt-1 text-h1 font-bold text-ink-hi">
                      {formatCompactVnd(SAR_DRAFT.inflow)} ₫
                    </div>
                    <StatusBadge tone="warn" label={SAR_DRAFT.inflowNote} />
                  </div>
                  <div className="rounded-panel border border-line bg-elev p-3.5">
                    <div className="text-2xs uppercase tracking-wide text-ink-low">
                      Đích tiền ra
                    </div>
                    <div className="tabular mt-1 text-h1 font-bold text-ink-hi">
                      {formatCompactVnd(SAR_DRAFT.outflow)} ₫
                    </div>
                    <StatusBadge tone="info" label={SAR_DRAFT.outflowNote} />
                  </div>
                </div>
                <div className="overflow-x-auto rounded-panel border border-line">
                  <table className="w-full min-w-[520px] text-left">
                    <thead>
                      <tr className="border-b border-line">
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
                      {SAR_DRAFT.relatedTransactions.map((t) => (
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
                <p className="text-2xs text-ink-low">
                  Số liệu do công cụ tính toán tổng hợp, không phải số do mô hình sinh.
                </p>
              </div>
            )}

            {tab === "customer" && (
              <div className="space-y-3 p-4">
                <div className="text-body-lg font-semibold text-ink-hi">Thông tin khách hàng</div>
                <dl className="grid grid-cols-2 gap-3 text-body">
                  <div>
                    <dt className="text-2xs uppercase tracking-wide text-ink-low">Chủ thể</dt>
                    <dd className="mt-0.5 font-medium text-ink-hi">{SAR_DRAFT.subjectName}</dd>
                  </div>
                  <div>
                    <dt className="text-2xs uppercase tracking-wide text-ink-low">Mã khách hàng</dt>
                    <dd className="tabular mt-0.5 font-medium text-ink-hi">{SAR_DRAFT.subject.customerId}</dd>
                  </div>
                  <div>
                    <dt className="text-2xs uppercase tracking-wide text-ink-low">Tài khoản</dt>
                    <dd className="tabular mt-0.5 font-medium text-ink-hi">{SAR_DRAFT.subject.accountKey}</dd>
                  </div>
                  <div>
                    <dt className="text-2xs uppercase tracking-wide text-ink-low">Vụ việc nguồn</dt>
                    <dd className="tabular mt-0.5 font-medium text-info">{SAR_DRAFT.case_id}</dd>
                  </div>
                </dl>
              </div>
            )}
          </Panel>
        </div>

        {/* Cột phải: Kiểm chứng + Thanh tra bằng chứng */}
        <div className="space-y-3">
          <ValidationPanel
            status={sarStatus}
            issues={sarStatus === "DRAFT" ? [] : sarIssues}
            onFix={async () => {
              try {
                await api.validateSar(SAR_DRAFT.sar_id);
                await sarQuery.reload();
                pushToast({ tone: "success", title: "Kiểm chứng lại thành công" });
              } catch (cause) {
                pushToast({ tone: "error", title: "Vẫn còn lỗi bằng chứng", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
              }
            }}
          />

          <Panel
            title="Thanh tra bằng chứng"
            action={<StatusBadge tone="primary" label="AI HỖ TRỢ" />}
            padded={false}
          >
            <div className="space-y-2 p-3">
              {inspectorItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setDrawerEvidence(item.evidence)}
                  className="w-full rounded-control border border-line bg-elev p-2.5 text-left hover:border-line-emphasis"
                >
                  <div className="tabular text-2xs text-ink-low">{item.id}</div>
                  <div className="mt-0.5 text-body font-medium text-ink-hi">{item.title}</div>
                  <div className="mt-1 flex gap-1">
                    {item.tags.map((tag) => (
                      <span
                        key={tag}
                        className={`rounded px-1.5 py-0.5 text-2xs ${
                          tag === "EXPIRED"
                            ? "bg-risk/15 text-risk"
                            : tag === "IP CLASH"
                              ? "bg-warn/15 text-warn"
                              : "bg-panel text-ink-mid"
                        }`}
                      >
                        {tag === "EXPIRED" ? "Hết hạn" : tag === "IP CLASH" ? "Trùng IP" : tag}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
              <div className="flex flex-col items-center gap-1.5 rounded-control border border-dashed border-line p-4 text-center">
                <FileUp size={16} className="text-ink-low" aria-hidden />
                <span className="text-2xs text-ink-mid">Kéo thả tài liệu chứng minh bổ sung</span>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      <EvidenceDrawer
        evidenceId={drawerEvidence}
        evidence={SAR_DRAFT.evidence}
        onClose={() => setDrawerEvidence(null)}
        onSelect={setDrawerEvidence}
      />

      <ReasonModal
        open={submitOpen}
        title={`Gửi ${SAR_DRAFT.sar_id} phê duyệt`}
        description={`Báo cáo sẽ chuyển sang trạng thái Chờ phê duyệt và gửi tới người phê duyệt. Người gửi (${currentUser?.name ?? ""}) sẽ không thể tự phê duyệt báo cáo này.`}
        confirmLabel="Gửi phê duyệt"
        onClose={() => setSubmitOpen(false)}
        onConfirm={async (reason) => {
          try {
            await api.submitSar(SAR_DRAFT.sar_id, reason);
            await sarQuery.reload();
            setSubmitOpen(false);
            pushToast({ tone: "success", title: `Đã gửi ${SAR_DRAFT.sar_id} tới hàng đợi phê duyệt`, detail: "Bản ghi phê duyệt và nhật ký kiểm toán đã được lưu trong cơ sở dữ liệu." });
            navigate("/approvals");
          } catch (cause) {
            pushToast({ tone: "error", title: "Không gửi được SAR", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
          }
        }}
      />
    </PageShell>
  );
}
