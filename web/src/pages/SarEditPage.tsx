import { FileDown, FileUp, Pencil, Play, Save, Send } from "lucide-react";
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
import {
  evidenceSourceLabel,
  evidenceSummary,
  evidenceTitle,
  formatAmountText,
  formatDateTime,
  formatMoney,
  paymentChannelLabel,
  customerTypeLabel,
  profileValueLabel,
  riskRatingLabel,
  formatDate,
} from "../api/format";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";

const TABS = [
  { id: "summary", label: "Tóm tắt" },
  { id: "flow", label: "Chi tiết luồng tiền" },
  { id: "customer", label: "Thông tin khách hàng" },
  // Ba mục cuối của hồ sơ (đồ thị, phê duyệt, phương pháp & giới hạn) trước nay
  // CHỈ tồn tại trong file PDF. Muốn biết bản báo cáo thật trông thế nào thì
  // phải xuất file ra xem — sửa xong không đối chiếu được ngay tại chỗ.
  { id: "preview", label: "Xem trước bản báo cáo" },
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
  // Chế độ SỬA bản nháp: chuyên viên chỉnh tóm tắt + nội dung từng nhận định.
  const [editing, setEditing] = useState(false);
  const [draftSummary, setDraftSummary] = useState("");
  const [draftFindings, setDraftFindings] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  // Người lập báo cáo: khai ngay tại tab xem trước, đúng chỗ nó xuất hiện trên
  // file PDF. `null` = chưa mở form, dùng giá trị đang lưu của hồ sơ.
  const [preparerForm, setPreparerForm] = useState<null | {
    name: string;
    title: string;
    department: string;
    phone: string;
    email: string;
  }>(null);
  const [savingPreparer, setSavingPreparer] = useState(false);

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
  // Nhãn nghiệp vụ cho mọi mã bằng chứng của hồ sơ — chip trong phần nhận định
  // tra bảng này thay vì in "EV-1f321dc25a6303e13d7a4315" ra màn hình.
  const evidenceLabels = Object.fromEntries(
    SAR_DRAFT.evidence.map((item) => [item.id, evidenceTitle(item.type, item.source)]),
  );
  const inspectorItems = SAR_DRAFT.evidence.slice(0, 6).map((item) => ({
    id: item.id,
    title: evidenceTitle(item.type, item.source),
    summary: evidenceSummary(item.type, item.payload),
    source: evidenceSourceLabel(item.source),
    alerts: item.tags.filter((tag) => tag === "EXPIRED" || tag === "IP CLASH"),
    evidence: item.id,
  }));

  const canSubmit = sarStatus === "VALIDATION_PASSED";
  const submitted =
    sarStatus === "PENDING_REVIEW" || sarStatus === "APPROVED" || sarStatus === "REJECTED";
  const canEdit = !submitted;

  const startEdit = () => {
    setDraftSummary(SAR_DRAFT.behaviourSummary);
    setDraftFindings(Object.fromEntries(SAR_DRAFT.statements.map((s) => [s.id, s.text])));
    setTab("summary");
    setEditing(true);
  };
  const saveNarrative = async () => {
    setSaving(true);
    try {
      await api.updateSarNarrative(
        SAR_DRAFT.sar_id,
        draftSummary,
        SAR_DRAFT.statements.map((s) => ({ id: s.id, text: draftFindings[s.id] ?? s.text })),
      );
      await sarQuery.reload();
      setEditing(false);
      pushToast({
        tone: "success",
        title: "Đã lưu bản nháp",
        detail: "Nhớ chạy kiểm chứng lại trước khi gửi phê duyệt.",
      });
    } catch (cause) {
      pushToast({
        tone: "error",
        title: "Không lưu được",
        detail: cause instanceof Error ? cause.message : "Lỗi không xác định",
      });
    } finally {
      setSaving(false);
    }
  };

  const savePreparer = async () => {
    if (!preparerForm) return;
    setSavingPreparer(true);
    try {
      await api.updateSarPreparer(SAR_DRAFT.sar_id, preparerForm);
      await sarQuery.reload();
      setPreparerForm(null);
      pushToast({
        tone: "success",
        title: "Đã lưu thông tin người lập",
        detail: "Họ tên và chức danh sẽ in ở phần đầu và khối ký của bản báo cáo.",
      });
    } catch (cause) {
      pushToast({
        tone: "error",
        title: "Không lưu được thông tin người lập",
        detail: cause instanceof Error ? cause.message : "Lỗi không xác định",
      });
    } finally {
      setSavingPreparer(false);
    }
  };

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
          {editing ? (
            <>
              <button
                type="button"
                disabled={saving}
                onClick={saveNarrative}
                className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-body font-semibold text-app hover:bg-primary-hover disabled:opacity-50"
              >
                <Save size={13} aria-hidden />
                {saving ? "Đang lưu…" : "Lưu bản nháp"}
              </button>
              <button
                type="button"
                disabled={saving}
                onClick={() => setEditing(false)}
                className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-mid hover:text-ink-hi disabled:opacity-50"
              >
                Huỷ
              </button>
            </>
          ) : (
            canEdit && (
              <button
                type="button"
                onClick={startEdit}
                title="Sửa tóm tắt và nội dung các nhận định của bản nháp"
                className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi hover:border-line-emphasis"
              >
                <Pencil size={13} aria-hidden />
                Sửa nội dung
              </button>
            )
          )}
          <button
            type="button"
            disabled={editing}
            onClick={async () => {
              try {
                await api.exportSar(SAR_DRAFT.sar_id);
                pushToast({ tone: "success", title: "Đã xuất PDF", detail: "Đọc lại báo cáo trước khi gửi phê duyệt." });
              } catch (cause) {
                pushToast({
                  tone: "error",
                  title: "Không xuất được PDF",
                  detail: cause instanceof Error ? cause.message : "Lỗi không xác định",
                });
              }
            }}
            title="Xuất PDF bản nháp để đọc/soát trước khi gửi phê duyệt"
            className="inline-flex items-center gap-1.5 rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-hi hover:border-line-emphasis"
          >
            <FileDown size={13} aria-hidden />
            Xuất PDF (đọc)
          </button>
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
                {editing && (
                  <div className="rounded-control border border-primary/30 bg-primary/[0.06] px-3 py-2 text-2xs text-ink-mid">
                    Đang sửa bản nháp. Chỉnh phần chữ tuỳ ý; liên kết bằng chứng của mỗi nhận định giữ nguyên. Bấm
                    <b className="text-ink-hi"> Lưu bản nháp</b> rồi <b className="text-ink-hi">Chạy kiểm chứng</b> trước khi gửi.
                  </div>
                )}
                <div>
                  <div className="mb-2 text-body-lg font-semibold text-ink-hi">Tóm tắt hành vi nghi vấn</div>
                  {editing ? (
                    <textarea
                      value={draftSummary}
                      onChange={(e) => setDraftSummary(e.target.value)}
                      rows={5}
                      className="w-full rounded-control border border-line bg-elev p-2.5 text-body leading-relaxed text-ink-hi focus:border-primary-line focus:outline-none"
                    />
                  ) : (
                    <p className="text-body leading-relaxed text-ink-mid">{SAR_DRAFT.behaviourSummary}</p>
                  )}
                </div>
                <div>
                  <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                    Nhận định kèm bằng chứng (câu thiếu bằng chứng bị chặn khi gửi)
                  </div>
                  <div className="space-y-2">
                    {SAR_DRAFT.statements.map((st) =>
                      editing ? (
                        <div key={st.id} className="rounded-control border border-line bg-elev p-2.5">
                          <textarea
                            value={draftFindings[st.id] ?? st.text}
                            onChange={(e) => setDraftFindings((m) => ({ ...m, [st.id]: e.target.value }))}
                            rows={2}
                            className="w-full resize-y rounded-control border border-line bg-panel p-2 text-body text-ink-hi focus:border-primary-line focus:outline-none"
                          />
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {st.evidenceIds.map((id) => (
                              <span key={id} className="rounded-control border border-line px-1.5 py-0.5 text-3xs text-ink-low">
                                bằng chứng đã gắn
                              </span>
                            ))}
                          </div>
                        </div>
                      ) : (
                        <SARStatement
                          key={st.id}
                          statement={st}
                          evidenceLabels={evidenceLabels}
                          onOpenEvidence={setDrawerEvidence}
                        />
                      ),
                    )}
                  </div>
                </div>
              </div>
            )}

            {tab === "flow" && (
              <div className="space-y-4 p-4">
                <div className="text-body-lg font-semibold text-ink-hi">Phân tích luồng tiền</div>
                {/* Tiền vào/ra tách THEO LOẠI TIỀN. Bản cũ cộng thẳng mọi loại
                    tiền thành một số rồi dán "₫" vào đuôi — vừa sai đơn vị vừa
                    là phép cộng không có nghĩa. Bản PDF đã tách từ trước. */}
                {SAR_DRAFT.flowByCurrency.length === 1 ? (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="rounded-panel border border-line bg-elev p-3.5">
                      <div className="text-2xs uppercase tracking-wide text-ink-low">
                        Nguồn tiền vào
                      </div>
                      <div className="tabular mt-1 text-h1 font-bold text-ink-hi">
                        {formatMoney(SAR_DRAFT.flowByCurrency[0].inflow)}{" "}
                        <span className="text-body-lg font-semibold text-ink-mid">
                          {SAR_DRAFT.flowByCurrency[0].currency}
                        </span>
                      </div>
                      <StatusBadge tone="warn" label={SAR_DRAFT.inflowNote} />
                    </div>
                    <div className="rounded-panel border border-line bg-elev p-3.5">
                      <div className="text-2xs uppercase tracking-wide text-ink-low">
                        Đích tiền ra
                      </div>
                      <div className="tabular mt-1 text-h1 font-bold text-ink-hi">
                        {formatMoney(SAR_DRAFT.flowByCurrency[0].outflow)}{" "}
                        <span className="text-body-lg font-semibold text-ink-mid">
                          {SAR_DRAFT.flowByCurrency[0].currency}
                        </span>
                      </div>
                      <StatusBadge tone="info" label={SAR_DRAFT.outflowNote} />
                    </div>
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-panel border border-line">
                    <table className="w-full min-w-[440px] text-left">
                      <thead>
                        <tr className="border-b border-line">
                          {["Loại tiền", "Tiền vào", "Tiền ra", "Số giao dịch"].map((h) => (
                            <th
                              key={h}
                              className="px-3 py-2 text-2xs font-semibold uppercase tracking-wide text-ink-low"
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {SAR_DRAFT.flowByCurrency.map((row) => (
                          <tr key={row.currency} className="border-b border-line/60 last:border-0">
                            <td className="px-3 py-2 text-body font-medium text-ink-hi">
                              {row.currency}
                            </td>
                            <td className="tabular px-3 py-2 text-body text-ink-hi">
                              {formatMoney(row.inflow)}
                            </td>
                            <td className="tabular px-3 py-2 text-body text-ink-hi">
                              {formatMoney(row.outflow)}
                            </td>
                            <td className="tabular px-3 py-2 text-body text-ink-mid">{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="overflow-x-auto rounded-panel border border-line">
                  <table className="w-full min-w-[520px] text-left">
                    <thead>
                      <tr className="border-b border-line">
                        {["Mã giao dịch", "Thời gian", "Số tiền", "Kênh"].map((h) => (
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
                          <td className="tabular px-3 py-2 text-body text-ink-mid">{formatDateTime(t.time)}</td>
                          <td className="tabular px-3 py-2 text-body text-ink-hi">{formatAmountText(t.amount)}</td>
                          <td className="px-3 py-2 text-body text-ink-mid">{paymentChannelLabel(t.location)}</td>
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

            {tab === "preview" && (
              <div className="space-y-4">
                <p className="rounded-control border border-line bg-elev p-3 text-2xs text-ink-mid">
                  Đúng thứ tự và nội dung của file PDF sẽ xuất ra. Sửa nội dung ở tab Tóm tắt, khai người lập
                  ngay tại mục I bên dưới, rồi đối chiếu trước khi gửi phê duyệt.
                </p>

                <ReportSection no="I" title="Thông tin chung về báo cáo">
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-2xs">
                    <ReportField label="Số hiệu báo cáo" value={SAR_DRAFT.sar_id} />
                    <ReportField label="Mã vụ việc" value={SAR_DRAFT.case_id} />
                    <ReportField label="Mã cảnh báo" value={SAR_DRAFT.alert_id} />
                    <ReportField label="Loại nghi vấn" value={SAR_DRAFT.suspicionType} />
                    <ReportField label="Mức rủi ro" value={SAR_DRAFT.riskLevel} />
                    <ReportField label="Nơi nhận" value={SAR_DRAFT.institution?.recipient} />
                  </dl>

                  <div className="mt-3 border-t border-line pt-3">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                        Người lập báo cáo
                      </span>
                      {!SAR_DRAFT.preparer?.declared && (
                        <StatusBadge tone="warn" label="CHƯA KHAI" />
                      )}
                      {canEdit && !preparerForm && (
                        <button
                          type="button"
                          onClick={() =>
                            setPreparerForm({
                              name: SAR_DRAFT.preparer?.name ?? "",
                              title: SAR_DRAFT.preparer?.title ?? "",
                              department: SAR_DRAFT.preparer?.department ?? "",
                              phone: SAR_DRAFT.preparer?.phone ?? "",
                              email: SAR_DRAFT.preparer?.email ?? "",
                            })
                          }
                          className="ml-auto inline-flex items-center gap-1.5 rounded-control border border-line px-2.5 py-1 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
                        >
                          <Pencil size={12} aria-hidden />
                          {SAR_DRAFT.preparer?.declared ? "Sửa thông tin" : "Khai thông tin"}
                        </button>
                      )}
                    </div>

                    {preparerForm ? (
                      <div className="space-y-2">
                        <div className="grid grid-cols-2 gap-2">
                          <PreparerField
                            label="Họ và tên"
                            required
                            value={preparerForm.name}
                            onChange={(v) => setPreparerForm({ ...preparerForm, name: v })}
                          />
                          <PreparerField
                            label="Chức danh"
                            value={preparerForm.title}
                            onChange={(v) => setPreparerForm({ ...preparerForm, title: v })}
                          />
                          <PreparerField
                            label="Đơn vị công tác"
                            value={preparerForm.department}
                            onChange={(v) => setPreparerForm({ ...preparerForm, department: v })}
                          />
                          <PreparerField
                            label="Điện thoại liên hệ"
                            value={preparerForm.phone}
                            onChange={(v) => setPreparerForm({ ...preparerForm, phone: v })}
                          />
                          <PreparerField
                            label="Thư điện tử"
                            value={preparerForm.email}
                            onChange={(v) => setPreparerForm({ ...preparerForm, email: v })}
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            type="button"
                            disabled={savingPreparer || preparerForm.name.trim().length < 2}
                            onClick={savePreparer}
                            className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-body font-semibold text-app hover:bg-primary-hover disabled:opacity-50"
                          >
                            <Save size={13} aria-hidden />
                            {savingPreparer ? "Đang lưu…" : "Lưu thông tin người lập"}
                          </button>
                          <button
                            type="button"
                            disabled={savingPreparer}
                            onClick={() => setPreparerForm(null)}
                            className="rounded-control border border-line px-3 py-1.5 text-body font-medium text-ink-mid hover:text-ink-hi disabled:opacity-50"
                          >
                            Huỷ
                          </button>
                          <span className="text-2xs text-ink-low">Họ tên là bắt buộc.</span>
                        </div>
                      </div>
                    ) : SAR_DRAFT.preparer?.declared ? (
                      <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-2xs">
                        <ReportField label="Họ và tên" value={SAR_DRAFT.preparer.name} />
                        <ReportField label="Chức danh" value={SAR_DRAFT.preparer.title || "—"} />
                        <ReportField label="Đơn vị công tác" value={SAR_DRAFT.preparer.department || "—"} />
                        <ReportField label="Điện thoại liên hệ" value={SAR_DRAFT.preparer.phone || "—"} />
                        <ReportField label="Thư điện tử" value={SAR_DRAFT.preparer.email || "—"} />
                      </dl>
                    ) : (
                      <p className="text-2xs text-ink-mid">
                        Chưa khai người lập báo cáo. Bản PDF sẽ để trống ô họ tên và khối ký — cần khai
                        trước khi gửi phê duyệt.
                      </p>
                    )}
                  </div>
                </ReportSection>

                <ReportSection no="II" title="Đối tượng bị báo cáo">
                  <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-2xs">
                    <ReportField label="Mã khách hàng" value={SAR_DRAFT.subject.customerId} />
                    <ReportField label="Tài khoản" value={SAR_DRAFT.subject.accountKey} />
                    {/* Đây là BẢN XEM TRƯỚC của hồ sơ gửi ra ngoài, nên không
                        chỗ nào được để lọt giá trị thô: `organisation`, `medium`,
                        `2022-09-07` hay tên bộ dữ liệu trong trường nghề nghiệp. */}
                    <ReportField
                      label="Loại khách hàng"
                      value={customerTypeLabel(SAR_DRAFT.subject.customerType)}
                    />
                    <ReportField
                      label="Nghề nghiệp / ngành nghề"
                      value={profileValueLabel(SAR_DRAFT.subject.occupation)}
                    />
                    <ReportField
                      label="Xếp hạng rủi ro nội bộ"
                      value={riskRatingLabel(SAR_DRAFT.subject.riskRating)}
                    />
                    <ReportField
                      label="Ngày thiết lập quan hệ"
                      value={formatDate(SAR_DRAFT.subject.onboardingDate)}
                    />
                  </dl>
                </ReportSection>

                <ReportSection no="III" title="Tóm tắt hành vi nghi vấn">
                  <p className="text-body leading-relaxed text-ink-mid">{SAR_DRAFT.behaviourSummary}</p>
                </ReportSection>

                <ReportSection no="IV" title="Nhận định và bằng chứng">
                  <ol className="space-y-2">
                    {SAR_DRAFT.statements.map((st, i) => (
                      <li key={st.id} className="text-body leading-relaxed text-ink-mid">
                        <span className="tabular mr-1.5 font-semibold text-ink-hi">{i + 1}.</span>
                        {st.text}
                        <div className="mt-0.5 text-2xs text-ink-low">
                          Căn cứ:{" "}
                          {st.evidenceIds.length > 0
                            ? Array.from(
                                new Set(st.evidenceIds.map((id) => evidenceLabels[id] ?? "Bằng chứng nghiệp vụ")),
                              ).join("; ")
                            : "chưa gắn bằng chứng"}
                        </div>
                      </li>
                    ))}
                  </ol>
                </ReportSection>

                <ReportSection no="V" title="Giao dịch liên quan">
                  <p className="text-2xs text-ink-mid">
                    {SAR_DRAFT.relatedTransactions.length} giao dịch được đưa vào hồ sơ, kèm bảng tổng hợp
                    dòng tiền theo từng loại tiền tệ. Xem đầy đủ ở tab “Chi tiết luồng tiền”.
                  </p>
                </ReportSection>

                <ReportSection no="VI" title="Sơ đồ quan hệ giao dịch">
                  <p className="text-2xs text-ink-mid">
                    Sơ đồ được dựng khi xuất file, từ các giao dịch của chính vụ này. Xem tương tác ở tab
                    “Đồ thị mạng lưới” trong trang vụ việc.
                  </p>
                </ReportSection>

                <ReportSection no="VII" title="Ý kiến phê duyệt">
                  <p className="text-2xs text-ink-mid">
                    {SAR_DRAFT.approval
                      ? "Kết luận, người phê duyệt và thời điểm phê duyệt sẽ in đầy đủ ở mục này."
                      : "Hồ sơ chưa có ý kiến phê duyệt — mục này sẽ ghi “chưa có ý kiến phê duyệt”."}
                  </p>
                </ReportSection>

                <ReportSection no="VIII" title="Phương pháp và giới hạn">
                  <p className="text-body leading-relaxed text-ink-mid">
                    Báo cáo do chuyên viên lập với hỗ trợ của trợ lý AI: phần tóm tắt và các nhận định được
                    soạn từ kết quả điều tra và chỉ trích dẫn bằng chứng có thật của vụ; chuyên viên đã rà
                    soát và chịu trách nhiệm nội dung. Mức rủi ro do bộ phát hiện chấm điểm, là tín hiệu hỗ
                    trợ rà soát — KHÔNG phải xác suất rửa tiền. Đây là báo cáo nghi vấn để cơ quan có thẩm
                    quyền xem xét, không phải kết luận về hành vi phạm tội.
                  </p>
                </ReportSection>

                <section className="rounded-control border border-line bg-elev p-3.5">
                  <h3 className="mb-2 text-body-lg font-semibold text-ink-hi">Khối ký cuối văn bản</h3>
                  <div className="grid grid-cols-2 gap-4 text-center text-2xs">
                    <div>
                      <div className="font-semibold uppercase tracking-wide text-ink-hi">Người lập báo cáo</div>
                      <div className="text-ink-low">(Ký, ghi rõ họ tên)</div>
                      <div className="mt-6 font-semibold text-ink-hi">
                        {SAR_DRAFT.preparer?.declared ? SAR_DRAFT.preparer.name : "— chưa khai —"}
                      </div>
                      <div className="text-ink-low">{SAR_DRAFT.preparer?.title}</div>
                    </div>
                    <div>
                      <div className="font-semibold uppercase tracking-wide text-ink-hi">Người phê duyệt</div>
                      <div className="text-ink-low">(Ký, ghi rõ họ tên)</div>
                      <div className="mt-6 font-semibold text-ink-hi">
                        {SAR_DRAFT.approval?.decision === "approved"
                          ? SAR_DRAFT.approval.decided_by
                          : "— chờ phê duyệt —"}
                      </div>
                    </div>
                  </div>
                </section>
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

        {/* Cột phải: Kiểm chứng + bằng chứng đối chiếu */}
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
            title="Bằng chứng đối chiếu"
            padded={false}
          >
            <div className="space-y-2.5 p-3">
              {inspectorItems.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setDrawerEvidence(item.evidence)}
                  aria-label={`Xem ${item.title.toLocaleLowerCase("vi-VN")}`}
                  className="group w-full min-w-0 rounded-control border border-line bg-elev p-3 text-left transition-colors duration-200 hover:border-primary-line hover:bg-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-line"
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span className="tabular mt-0.5 shrink-0 text-2xs font-semibold text-primary">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-body-lg font-semibold leading-snug text-ink-hi">
                        {item.title}
                      </div>
                      <p className="mt-1 break-words text-body leading-relaxed text-ink-mid">
                        {item.summary}
                      </p>
                    </div>
                  </div>

                  {item.alerts.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1 pl-7">
                      {item.alerts.map((tag) => (
                      <span
                        key={tag}
                        className={`rounded px-1.5 py-0.5 text-2xs font-medium ${
                          tag === "EXPIRED"
                            ? "bg-risk/15 text-risk"
                            : "bg-warn/15 text-warn"
                        }`}
                      >
                        {tag === "EXPIRED" ? "Hết hạn" : tag === "IP CLASH" ? "Trùng IP" : tag}
                      </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-2.5 flex min-w-0 items-center justify-between gap-3 border-t border-line/60 pt-2 pl-7 text-2xs">
                    <span className="min-w-0 truncate text-ink-low" title={item.source}>
                      Nguồn: {item.source}
                    </span>
                    <span className="shrink-0 font-medium text-info transition-colors group-hover:text-primary">
                      Xem chi tiết →
                    </span>
                  </div>
                </button>
              ))}
              {inspectorItems.length === 0 && (
                <div className="rounded-control border border-dashed border-line px-4 py-5 text-center">
                  <p className="text-body font-medium text-ink-hi">Chưa có bằng chứng để kiểm chứng</p>
                  <p className="mt-1 text-2xs text-ink-mid">Bằng chứng do hệ thống thu thập sẽ xuất hiện tại đây.</p>
                </div>
              )}
              <div className="flex flex-col items-center gap-1.5 rounded-control border border-dashed border-line p-4 text-center">
                <FileUp size={16} className="text-ink-low" aria-hidden />
                <span className="text-body font-medium text-ink-mid">Bổ sung tài liệu chứng minh</span>
                <span className="text-2xs text-ink-low">Kéo thả tệp vào đây để đính kèm</span>
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

/** Một mục của hồ sơ SAR, đánh số khớp file PDF để đối chiếu được từng mục. */
function ReportSection({ no, title, children }: { no: string; title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-control border border-line bg-elev p-3.5">
      <h3 className="mb-2 text-body-lg font-semibold text-ink-hi">
        <span className="tabular mr-1.5 text-primary">{no}.</span>
        {title}
      </h3>
      {children}
    </section>
  );
}

/** Ô nhập một dòng cho khối "Người lập báo cáo". */
function PreparerField({
  label,
  value,
  onChange,
  required,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-2xs text-ink-low">
        {label}
        {required && <span className="text-risk"> *</span>}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-0.5 w-full rounded-control border border-line bg-panel px-2 py-1.5 text-body text-ink-hi focus:border-primary-line focus:outline-none"
      />
    </label>
  );
}

function ReportField({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <>
      <dt className="text-ink-low">{label}</dt>
      <dd className="font-medium text-ink-hi">{value ?? "—"}</dd>
    </>
  );
}
