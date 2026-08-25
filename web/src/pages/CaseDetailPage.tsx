import { ArrowLeft, CheckCircle2, Circle, FileText, Loader2, PlayCircle, RefreshCw, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, api, num } from "../api/client";
import {
  caseDisplayTitle,
  caseStateLabel,
  caseStepLabel,
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

/** Sau khi giao tác vụ, hỏi lại máy chủ tới khi trạng thái đổi. Worker chạy
 *  nền nên thời điểm xong không đoán trước được từ phía trình duyệt. */
const POLL_INTERVAL_MS = 1200;
const POLL_ATTEMPTS = 15;

/** Trần số bước tự chạy — chuỗi tự động dài 8 bước (Tiếp nhận → Chờ phê duyệt);
 *  đặt dư để chặn vòng lặp vô hạn nếu worker kẹt. */
const MAX_AUTO_STEPS = 12;

/** Trạng thái mà chuỗi tự động phải DỪNG: cổng phê duyệt của con người và mọi
 *  trạng thái kết thúc. Không có cung máy nào bước qua đây — vào Xuất hồ sơ đòi
 *  quyết định có người ký tên (NT3). Khớp src/domain.py (next_state → None). */
const AUTO_STOP_STATES = new Set([
  "ChoNguoiPheDuyet",
  "XuatHoSo",
  "DongKhongBaoCao",
  "DieuTraBoSung",
]);

export function CaseDetailPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const { pushToast, currentUser } = useApp();

  const detail = useApi(() => api.case(caseId ?? ""), [caseId]);
  const audit = useApi(() => api.audit({ case_id: caseId, limit: 50 }), [caseId]);
  const [running, setRunning] = useState(false);
  // Nút soạn SAR ngay trên Chi tiết vụ việc — trước đây chỉ có ở trang Đồ thị
  // mạng lưới nên analyst khó tìm, hàng đợi phê duyệt của quản lý luôn rỗng.
  const [sarModal, setSarModal] = useState(false);
  const canPrepareSar = currentUser?.permissions?.includes(PERMISSIONS.PREPARE_SAR) ?? false;

  // Dọn timer khi rời trang giữa lúc còn đang hỏi vòng.
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach(window.clearTimeout), []);

  const reloadAll = useCallback(() => {
    detail.reload();
    audit.reload();
  }, [detail, audit]);

  /** Ngủ `ms` mili-giây, có đăng ký timer để dọn khi rời trang giữa chừng. */
  const sleep = useCallback(
    (ms: number) =>
      new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, ms);
        timers.current.push(timer);
      }),
    [],
  );

  // Chạy TOÀN BỘ chuỗi điều tra bằng một lần bấm: lặp lại "đẩy một bước → chờ
  // worker chuyển trạng thái" cho tới CỔNG phê duyệt của con người. Mỗi bước vẫn
  // là một tác vụ Redis riêng và một dòng nhật ký kiểm toán riêng — chỉ tự động
  // hoá thao tác bấm, không gộp bước, không bước qua NT3 (chuỗi tự dừng ở
  // ChoNguoiPheDuyet vì backend trả 409 khi next_state là None).
  const runInvestigation = useCallback(async () => {
    if (!caseId || running) return;
    setRunning(true);

    let stepsRun = 0;
    let lastState = detail.data?.state ?? "";
    let hadError = false;

    try {
      for (let guard = 0; guard < MAX_AUTO_STEPS; guard++) {
        // Đọc trạng thái mới nhất từ server, không tin bản cache trong lúc lặp.
        let current: string;
        try {
          current = (await api.case(caseId)).state;
        } catch {
          break;
        }
        lastState = current;
        // Tới cổng phê duyệt / trạng thái kết thúc thì dừng — không tự bước qua NT3.
        if (AUTO_STOP_STATES.has(current)) break;

        try {
          await api.investigate(caseId);
        } catch (cause) {
          // 409 = worker đã ở cổng phê duyệt: dừng êm, không coi là lỗi.
          if (cause instanceof ApiError && cause.status === 409) break;
          hadError = true;
          pushToast({
            tone: "error",
            title: "Không giao được tác vụ",
            detail: cause instanceof ApiError ? cause.message : "Lỗi không xác định",
          });
          break;
        }

        // Chờ worker nhích sang trạng thái mới; reload timeline để thấy tiến độ
        // ngay khi từng bước xong, thay vì đợi tới cuối.
        let advanced = false;
        for (let attempt = 1; attempt <= POLL_ATTEMPTS; attempt++) {
          await sleep(POLL_INTERVAL_MS);
          try {
            const fresh = await api.case(caseId);
            if (fresh.state !== current) {
              advanced = true;
              stepsRun += 1;
              lastState = fresh.state;
              detail.reload();
              audit.reload();
              break;
            }
          } catch {
            /* thử lại ở lượt sau */
          }
        }
        if (!advanced) break; // worker chưa xong sau nhiều lượt → dừng để không kẹt vòng
      }
    } finally {
      setRunning(false);
      reloadAll();
    }

    if (!hadError) {
      pushToast(
        stepsRun === 0
          ? {
              tone: "info",
              title: "Không có bước nào để chạy",
              detail: "Vụ việc đã ở cổng phê duyệt hoặc đã kết thúc.",
            }
          : {
              tone: "success",
              title: `Đã chạy xong ${stepsRun} bước điều tra`,
              detail:
                lastState === "ChoNguoiPheDuyet"
                  ? "Dừng ở Chờ người phê duyệt — cần người ký duyệt (NT3)."
                  : `Dừng ở ${caseStateLabel(lastState)}.`,
            },
      );
    }
  }, [caseId, running, detail, audit, pushToast, reloadAll, sleep]);

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
                      Đang chạy…
                    </>
                  ) : (
                    <>
                      <PlayCircle size={12} aria-hidden />
                      Chạy các bước tự động
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
                      {/* Nhãn nghiệp vụ (caseStepLabel) thay cho nhãn kỹ thuật
                          của backend: "Tính toán bằng công cụ" → "Phân tích định
                          lượng chỉ số", v.v. */}
                      {caseStepLabel(step.state)}
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
                Nút này chạy các bước điều tra <b className="text-ink-mid">được đề xuất</b> cho vụ này theo thứ tự — mỗi
                bước là một tác vụ riêng và một dòng nhật ký kiểm toán riêng; không phải vụ nào cũng đi hết chuỗi. Chuỗi
                tự dừng ở <em>Chờ người phê duyệt</em>: bước <em>Lập báo cáo SAR/STR</em> phải là quyết định có người ký
                tên (NT3), tách khỏi bước soạn tóm tắt điều tra. Bước đối chiếu trừng phạt/PEP hiện chạy trên dữ liệu
                tổng hợp minh hoạ, chưa nối nguồn danh sách thật.
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
