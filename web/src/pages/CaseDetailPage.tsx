import { ArrowLeft, CheckCircle2, Circle, Loader2, PlayCircle, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, api, num } from "../api/client";
import {
  caseStateLabel,
  countryLabel,
  formatAmount,
  formatDate,
  formatDateTime,
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

/** Sau khi giao tác vụ, hỏi lại máy chủ tới khi trạng thái đổi. Worker chạy
 *  nền nên thời điểm xong không đoán trước được từ phía trình duyệt. */
const POLL_INTERVAL_MS = 1200;
const POLL_ATTEMPTS = 15;

export function CaseDetailPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { pushToast } = useApp();

  const detail = useApi(() => api.case(caseId ?? ""), [caseId]);
  const audit = useApi(() => api.audit({ case_id: caseId, limit: 50 }), [caseId]);
  const [running, setRunning] = useState(false);

  // Dọn timer khi rời trang giữa lúc còn đang hỏi vòng.
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const reloadAll = useCallback(() => {
    detail.reload();
    audit.reload();
  }, [detail, audit]);

  const runInvestigation = useCallback(async () => {
    if (!caseId || running) return;
    const before = detail.data?.state;
    setRunning(true);

    try {
      await api.investigate(caseId);
      pushToast({
        tone: "info",
        title: "Đã giao tác vụ cho worker",
        detail: "Tác vụ vào hàng đợi Redis, worker nền đang xử lý.",
      });
    } catch (cause) {
      setRunning(false);
      pushToast({
        tone: "error",
        title: "Không giao được tác vụ",
        detail: cause instanceof ApiError ? cause.message : "Lỗi không xác định",
      });
      return;
    }

    // Hỏi lại tới khi trạng thái khác lúc bấm, hoặc hết lượt.
    for (let attempt = 1; attempt <= POLL_ATTEMPTS; attempt++) {
      const settled = await new Promise<boolean>((resolve) => {
        const timer = window.setTimeout(async () => {
          try {
            const fresh = await api.case(caseId);
            if (fresh.state !== before) {
              pushToast({
                tone: "success",
                title: "Worker đã chạy xong một bước",
                detail: `${caseStateLabel(before ?? "")} → ${caseStateLabel(fresh.state)}`,
              });
              resolve(true);
              return;
            }
          } catch {
            /* thử lại ở lượt sau */
          }
          resolve(false);
        }, POLL_INTERVAL_MS);
        timers.current.push(timer);
      });
      if (settled) break;
    }

    setRunning(false);
    reloadAll();
  }, [caseId, running, detail.data?.state, pushToast, reloadAll]);

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
  const awaitingApproval = k.timeline.every((s) => s.status !== "pending");

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
          <p className="mt-0.5 text-body text-ink-mid">{k.title}</p>
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
        </div>
      </div>

      <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
        <div className="space-y-3">
          {/* Máy trạng thái + nút chạy một bước điều tra */}
          <Panel
            title="Tiến trình điều tra"
            action={
              awaitingApproval ? (
                <StatusBadge tone="warn" label="Chờ người phê duyệt" />
              ) : (
                <button
                  type="button"
                  onClick={runInvestigation}
                  disabled={running}
                  className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {running ? (
                    <>
                      <Loader2 size={12} className="animate-spin" aria-hidden />
                      Worker đang chạy…
                    </>
                  ) : (
                    <>
                      <PlayCircle size={12} aria-hidden />
                      Chạy bước điều tra
                    </>
                  )}
                </button>
              )
            }
          >
            <ol className="relative ml-2 space-y-3 border-l border-line pl-5">
              {k.timeline.map((step) => (
                <li key={step.state} className="relative">
                  <span
                    aria-hidden
                    className={`absolute -left-[27px] top-0.5 ${
                      step.status === "done"
                        ? "text-ok"
                        : step.status === "active"
                          ? "text-primary"
                          : "text-ink-low"
                    }`}
                  >
                    {step.status === "done" ? (
                      <CheckCircle2 size={14} />
                    ) : step.status === "active" ? (
                      <Loader2 size={14} className={running ? "animate-spin" : ""} />
                    ) : (
                      <Circle size={14} />
                    )}
                  </span>
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`text-body ${
                        step.status === "pending" ? "text-ink-low" : "font-semibold text-ink-hi"
                      }`}
                    >
                      {step.label}
                    </span>
                    {step.status === "active" && <StatusBadge tone="primary" label="Hiện tại" />}
                  </div>
                  {step.occurred_at && (
                    <div className="tabular mt-0.5 text-2xs text-ink-low">
                      {formatDateTime(step.occurred_at)}
                    </div>
                  )}
                </li>
              ))}
            </ol>

            {/* Icon và đoạn văn là hai flex item; phần chữ phải nằm trong một
                thẻ bọc, nếu không mỗi <em> bên trong lại thành một flex item
                riêng và câu vỡ thành từng cột. */}
            <div className="mt-4 flex items-start gap-1.5 border-t border-line pt-3 text-2xs text-ink-low">
              <ShieldAlert size={12} className="mt-0.5 shrink-0" aria-hidden />
              <p>
                Mỗi lần bấm đẩy một tác vụ vào Redis; worker nền chuyển vụ việc sang trạng thái kế tiếp và ghi
                một dòng vào nhật ký kiểm toán. Chuỗi dừng ở <em>Chờ người phê duyệt</em> — lối vào{" "}
                <em>Xuất hồ sơ</em> phải là quyết định có người ký tên (NT3), không phải một lượt chạy tự động.
              </p>
            </div>
          </Panel>

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
              <Field label="Số cảnh báo" value={String(k.alert_count)} mono />
              <Field label="Số bằng chứng" value={String(k.evidence_count)} mono />
              <Field label="Phụ trách" value={k.assigned_to ?? "Chưa giao"} />
              <Field label="Mở lúc" value={formatDateTime(k.created_at)} />
            </dl>
          </Panel>

          {k.alert_ids.length > 0 && (
            <Panel title="Cảnh báo trong vụ việc">
              <ul className="space-y-1.5">
                {k.alert_ids.map((id) => (
                  <li key={id}>
                    <button
                      type="button"
                      onClick={() => navigate(`/alerts/${id}`)}
                      className="tabular w-full rounded-control border border-line bg-elev px-2.5 py-1.5 text-left text-2xs text-info hover:border-line-emphasis"
                    >
                      {id}
                    </button>
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
