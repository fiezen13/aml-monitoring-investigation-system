import { ArrowLeft, FileText, RefreshCw } from "lucide-react";
import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, num } from "../api/client";
import {
  caseDisplayTitle,
  caseStateLabel,
  countryLabel,
  formatAmount,
  formatDate,
  formatDateTime,
  formatRelative,
  initials,
  priorityLabel,
  profileValueLabel,
  prototypeLabel,
  riskRatingLabel,
} from "../api/format";
import { useApi } from "../api/useApi";
import { PageShell } from "../components/ui";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { AuditFeed } from "../components/common/AuditFeed";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { ReasonModal } from "../components/common/ReasonModal";
import { InvestigationPanel } from "../components/investigation/InvestigationPanel";
import { PERMISSIONS } from "../rbac/permissions";
import { useApp } from "../context/AppContext";

const PRIORITY_TONE: Record<string, "risk" | "warn" | "ok" | "muted"> = {
  critical: "risk",
  high: "risk",
  medium: "warn",
  low: "muted",
};

const RISK_RATING_TONE: Record<string, "risk" | "warn" | "ok"> = {
  high: "risk",
  medium: "warn",
  low: "ok",
};

export function CaseDetailPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { pushToast, currentUser } = useApp();

  const detail = useApi(() => api.case(caseId ?? ""), [caseId]);
  const audit = useApi(() => api.audit({ case_id: caseId, limit: 50 }), [caseId]);
  // Nút soạn SAR ngay trên Chi tiết vụ việc — trước đây chỉ có ở trang Đồ thị
  // mạng lưới nên analyst khó tìm, hàng đợi phê duyệt của quản lý luôn rỗng.
  const [sarModal, setSarModal] = useState(false);
  const canPrepareSar = currentUser?.permissions?.includes(PERMISSIONS.PREPARE_SAR) ?? false;

  const reloadAll = useCallback(() => {
    detail.reload();
    audit.reload();
  }, [detail, audit]);

  if (detail.loading) {
    return (
      <PageShell>
        <LoadingSkeleton rows={8} />
      </PageShell>
    );
  }

  if (detail.error || !detail.data) {
    return (
      <PageShell>
        {detail.error?.includes("Không tìm thấy") ? (
          <EmptyState title="Không tìm thấy vụ việc" detail={`Vụ việc "${caseId}" không tồn tại.`} />
        ) : (
          <ErrorState detail={detail.error ?? "Không tải được vụ việc"} onRetry={detail.reload} />
        )}
      </PageShell>
    );
  }

  const k = detail.data;
  const c = k.customer;
  // Trang Vụ việc là NƠI DUY NHẤT xem chi tiết (hàng đợi cảnh báo chỉ để sàng).
  // Điều tra AI chạy trên cảnh báo chính của vụ — 1 vụ ~ 1 cảnh báo trong hệ hiện tại.
  const primaryAlertId = k.alert_ids[0] ?? null;

  // Nhóm hành vi chính của vụ = typology xuất hiện nhiều nhất trong các yếu tố.
  // Giúp tóm tắt trả lời "vụ này về hành vi gì" thay vì chỉ số cảnh báo/bằng chứng.
  const primaryTypology = (() => {
    const counts = new Map<string, number>();
    for (const r of k.reasons) {
      if (r.typology_code) counts.set(r.typology_code, (counts.get(r.typology_code) ?? 0) + 1);
    }
    let best: string | null = null;
    let bestN = 0;
    for (const [code, n] of counts) if (n > bestN) [best, bestN] = [code, n];
    return best;
  })();

  return (
    <PageShell>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button
            type="button"
            onClick={() => navigate("/alerts")}
            className="mb-1.5 inline-flex items-center gap-1 text-2xs text-ink-mid hover:text-ink-hi"
          >
            <ArrowLeft size={12} aria-hidden />
            Hàng đợi cảnh báo
          </button>
          <h1 className="tabular text-h2 font-bold text-ink-hi">{k.case_id}</h1>
          <p className="mt-0.5 text-body text-ink-mid" title={k.title}>
            {caseDisplayTitle(k.title, k.subject_account_key)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="primary" label={caseStateLabel(k.state)} />
          <StatusBadge tone={PRIORITY_TONE[k.priority] ?? "muted"} label={`Ưu tiên: ${priorityLabel(k.priority)}`} />
          <RiskBadge score={Math.round(num(k.risk_score))} />
          <button
            type="button"
            onClick={reloadAll}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
          >
            <RefreshCw size={12} aria-hidden />
            Làm mới
          </button>
          {canPrepareSar && k.state !== "XuatHoSo" && k.state !== "DongKhongBaoCao" && (
            <button
              type="button"
              onClick={() => setSarModal(true)}
              className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover"
            >
              <FileText size={12} aria-hidden />
              Soạn hồ sơ SAR
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {/* Điều tra bằng AI thật (đa tác tử) — thay cho dải "chạy các bước"
              cũ vốn chỉ nhích trạng thái mà không phân tích gì. Đây là nơi
              chuyên viên đọc bản tóm tắt, dữ kiện/suy luận, bằng chứng và ra
              quyết định. Chạy trên cảnh báo chính của vụ. */}
          {primaryAlertId ? (
            <InvestigationPanel alertId={primaryAlertId} />
          ) : (
            <Panel title="Điều tra bằng AI">
              <EmptyState
                title="Vụ việc chưa gắn cảnh báo"
                detail="Chưa có cảnh báo nào trong vụ để chạy điều tra bằng AI."
              />
            </Panel>
          )}

          <Panel title="Yếu tố đóng góp vào điểm rủi ro">
            {k.reasons.length === 0 ? (
              <EmptyState title="Không có yếu tố" detail="Vụ việc chưa có cảnh báo kèm yếu tố đóng góp." />
            ) : (
              <div className="space-y-2">
                {k.reasons.map((r, i) => (
                  <div
                    key={`${r.factor_code}-${i}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded-control border border-line bg-elev px-3 py-2 text-2xs"
                  >
                    <span className="text-ink-hi">{r.factor_label}</span>
                    <span className="tabular text-ink-mid">
                      <span className="font-semibold text-ink-hi">{num(r.contribution).toFixed(2)}</span> · trọng
                      số {num(r.weight).toFixed(2)} · {r.typology_code}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel title="Nhật ký kiểm toán">
            {audit.loading ? (
              <LoadingSkeleton rows={4} />
            ) : audit.error ? (
              <ErrorState detail={audit.error} onRetry={audit.reload} />
            ) : (
              <AuditFeed events={audit.data ?? []} />
            )}
          </Panel>
        </div>

        <div className="space-y-3">
          <Panel title="Tóm tắt hồ sơ">
            <dl className="space-y-2 text-2xs">
              <Field label="Tài khoản chủ thể" value={k.subject_account_key} mono />
              <Field label="Nhóm hành vi chính" value={primaryTypology ?? "Chưa xác định"} />
              <div className="flex items-center justify-between gap-2">
                <dt className="text-ink-mid">Ưu tiên</dt>
                <dd>
                  <StatusBadge tone={PRIORITY_TONE[k.priority] ?? "muted"} label={priorityLabel(k.priority)} />
                </dd>
              </div>
              <Field label="Số cảnh báo" value={String(k.alert_count)} mono />
              <Field label="Số bằng chứng" value={String(k.evidence_count)} mono />
              <Field label="Phụ trách" value={k.assigned_to ?? "Chưa giao"} />
              <Field label="Tuổi hồ sơ" value={formatRelative(k.created_at)} />
              <Field label="Mở lúc" value={formatDateTime(k.created_at)} />
            </dl>
          </Panel>

          {k.alert_ids.length > 0 && (
            <Panel title="Cảnh báo trong vụ việc">
              {/* Chỉ để hiển thị — chi tiết đã ở ngay trang này, không dẫn đi
                  đâu nữa (tránh vòng lặp trở lại chính vụ việc). */}
              <ul className="space-y-1.5">
                {k.alert_ids.map((id) => (
                  <li
                    key={id}
                    className="tabular w-full rounded-control border border-line bg-elev px-2.5 py-1.5 text-2xs text-ink-mid"
                  >
                    {id}
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {c && (
            <Panel title="Hồ sơ chủ thể">
              <div className="mb-3 flex items-center gap-2.5">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-elev text-body font-bold text-primary">
                  {initials(c.customer_id)}
                </span>
                <div>
                  <div className="tabular text-body-lg font-semibold text-ink-hi">{c.customer_id}</div>
                  <div className="text-2xs text-ink-mid">{profileValueLabel(c.occupation)}</div>
                </div>
              </div>
              <dl className="space-y-2 text-2xs">
                <Field label="Nguyên mẫu" value={prototypeLabel(c.prototype)} />
                <Field label="Thu nhập khai báo" value={profileValueLabel(c.declared_income_band)} />
                <Field label="Doanh số kỳ vọng/tháng" value={formatAmount(c.expected_monthly_volume)} mono />
                <Field label="Quốc gia đăng ký" value={countryLabel(c.registered_country)} />
                <Field label="Ngày mở hồ sơ" value={formatDate(c.onboarding_date)} />
                <div className="flex items-center justify-between pt-1">
                  <dt className="text-ink-mid">Mức rủi ro hồ sơ</dt>
                  <dd>
                    <StatusBadge
                      tone={RISK_RATING_TONE[c.risk_rating] ?? "muted"}
                      label={riskRatingLabel(c.risk_rating)}
                    />
                  </dd>
                </div>
              </dl>
            </Panel>
          )}
        </div>
      </div>

      <ReasonModal
        open={sarModal}
        title="Soạn hồ sơ nghi vấn (SAR)"
        description="Tạo bản nháp SAR cho vụ việc này rồi mở trang soạn để kiểm chứng bằng chứng và nộp cho người phê duyệt (NT3). Nhập lý do để ghi vào nhật ký kiểm toán."
        confirmLabel="Tạo & mở bản nháp SAR"
        onClose={() => setSarModal(false)}
        onConfirm={async () => {
          try {
            const sar = await api.createSar(k.case_id);
            setSarModal(false);
            pushToast({ tone: "success", title: `Đã mở ${sar.sar_id}`, detail: "Bản nháp + bằng chứng + nhật ký đã ghi vào DB." });
            navigate(`/sar/${sar.sar_id}/edit`);
          } catch (cause) {
            pushToast({ tone: "error", title: "Không tạo được SAR", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
          }
        }}
      />
    </PageShell>
  );
}

function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-ink-mid">{label}</dt>
      <dd className={`text-right text-ink-hi ${mono ? "tabular" : ""}`}>{value}</dd>
    </div>
  );
}
