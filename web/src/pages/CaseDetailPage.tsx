import { ArrowLeft, FileText, RefreshCw } from "lucide-react";
import { lazy, Suspense, useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, num } from "../api/client";
import type { ApiWorkload } from "../api/client";
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
import { TYPOLOGY_LABELS } from "../api/typologyLabels";
import { PageShell } from "../components/ui";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { ReasonModal } from "../components/common/ReasonModal";
import { InvestigationPanel } from "../components/investigation/InvestigationPanel";
import { Tabs } from "../components/common/Tabs";
// Lazy: đồ thị Cytoscape (feature nặng) — chỉ tải khi mở tab Đồ thị. Đây đúng
// là "Đồ thị mạng lưới" giàu tính năng, nhưng gieo mầm theo chủ thể của vụ
// (prop subject) nên chỉ vẽ mạng lưới quanh vụ đang xem.
const InvestigationGraph = lazy(() =>
  import("../features/network-graph").then((m) => ({ default: m.InvestigationGraph })),
);
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
  // Nút soạn SAR ngay trên Chi tiết vụ việc — trước đây chỉ có ở trang Đồ thị
  // mạng lưới nên analyst khó tìm, hàng đợi phê duyệt của quản lý luôn rỗng.
  const [sarModal, setSarModal] = useState(false);
  const [tab, setTab] = useState("profile");
  const canPrepareSar = currentUser?.permissions?.includes(PERMISSIONS.PREPARE_SAR) ?? false;

  const reloadAll = useCallback(() => {
    detail.reload();
  }, [detail]);

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
            onClick={() => navigate("/cases")}
            className="mb-1.5 inline-flex items-center gap-1 text-2xs text-ink-mid hover:text-ink-hi"
          >
            <ArrowLeft size={12} aria-hidden />
            Danh sách vụ việc
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

      <Tabs
        tabs={[
          { id: "profile", label: "Hồ sơ điều tra" },
          { id: "graph", label: "Đồ thị mạng lưới" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "profile" && (
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
                      số {num(r.weight).toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {/* Nhật ký kiểm toán đã bỏ khỏi trang này: nó có trang riêng ở
              /audit, và ở đây nó đẩy phần nghiệp vụ xuống dưới một danh sách
              dài toàn dòng "Xem hồ sơ · api · Hệ thống" — tiếng ồn kỹ thuật do
              chính việc mở trang sinh ra, không giúp gì cho việc rà soát vụ. */}
        </div>

        <div className="space-y-3">
          <Panel title="Tóm tắt hồ sơ">
            <dl className="space-y-2 text-2xs">
              <Field label="Tài khoản chủ thể" value={k.subject_account_key} mono />
              <Field
                label="Nhóm hành vi chính"
                value={primaryTypology ? (TYPOLOGY_LABELS[primaryTypology]?.name ?? primaryTypology) : "Chưa xác định"}
              />
              <div className="flex items-center justify-between gap-2">
                <dt className="text-ink-mid">Ưu tiên</dt>
                <dd>
                  <StatusBadge tone={PRIORITY_TONE[k.priority] ?? "muted"} label={priorityLabel(k.priority)} />
                </dd>
              </div>
              <Field label="Số cảnh báo" value={String(k.alert_count)} mono />
              <Field label="Số bằng chứng" value={String(k.evidence_count)} mono />
              <AssignmentField
                caseId={k.case_id}
                assignedTo={k.assigned_to}
                assignedName={k.assigned_name}
                closed={CLOSED_CASE_STATES.has(k.state)}
                onChanged={() => detail.reload()}
              />
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
      )}

      {tab === "graph" && (
        <Suspense fallback={<div className="p-6 text-body text-ink-mid">Đang nạp đồ thị…</div>}>
          <div className="h-[calc(100vh-190px)] min-h-[520px] overflow-hidden rounded-panel border border-line">
            <InvestigationGraph subject={k.subject_account_key} caseId={k.case_id} />
          </div>
        </Suspense>
      )}

      <ReasonModal
        open={sarModal}
        title="Soạn hồ sơ nghi vấn (SAR)"
        description="Tạo bản nháp SAR cho vụ việc này rồi mở trang soạn để kiểm chứng bằng chứng và nộp cho người phê duyệt. Nhập lý do để ghi vào nhật ký kiểm toán."
        confirmLabel="Tạo & mở bản nháp SAR"
        onClose={() => setSarModal(false)}
        onConfirm={async () => {
          try {
            const sar = await api.createSar(k.case_id);
            setSarModal(false);
            pushToast({ tone: "success", title: `Đã mở ${sar.sar_id}`, detail: "Đã tạo bản nháp SAR kèm bằng chứng và nhật ký." });
            navigate(`/sar/${sar.sar_id}/edit`);
          } catch (cause) {
            pushToast({ tone: "error", title: "Không tạo được SAR", detail: cause instanceof Error ? cause.message : "Lỗi không xác định" });
          }
        }}
      />
    </PageShell>
  );
}

/** Vụ đã kết thúc thì không giao được nữa — khớp `_CLOSED_CASE_STATES` ở máy chủ. */
const CLOSED_CASE_STATES = new Set(["XuatHoSo", "DongKhongBaoCao"]);

/** Trường "Phụ trách" kèm thao tác giao việc ngay tại chỗ.
 *
 * Quản lý chọn người trong danh sách kèm SỐ VỤ ĐANG GIỮ của từng người — giao
 * việc mà không thấy ai đang gánh bao nhiêu thì chỉ là đoán. Chuyên viên chỉ có
 * hai nút: nhận vụ chưa ai giữ, hoặc trả lại vụ của chính mình.
 */
function AssignmentField({
  caseId,
  assignedTo,
  assignedName,
  closed,
  onChanged,
}: {
  caseId: string;
  assignedTo: string | null;
  assignedName: string | null;
  closed: boolean;
  onChanged: () => void;
}) {
  const { currentUser, pushToast } = useApp();
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const isManager = currentUser?.role === "manager";
  // Danh sách người để "Giao cho…" chỉ Quản lý mới dùng; Chuyên viên chỉ tự
  // nhận hoặc trả vụ, không cần biết ai đang gánh gì. API cũng đã khoá
  // "/workload" lại cho Quản lý nên Chuyên viên gọi vào sẽ nhận 403.
  const team = useApi<ApiWorkload | null>(
    () => (isManager ? api.workload() : Promise.resolve(null)),
    [isManager],
  );
  const isMine = assignedTo != null && assignedTo === currentUser?.id;

  const apply = async (assignee: string | null, reason: string) => {
    setBusy(true);
    try {
      await api.assignCase(caseId, assignee, reason);
      setPicking(false);
      onChanged();
      pushToast({
        tone: "success",
        title: assignee ? "Đã giao vụ việc" : "Đã trả vụ về hàng đợi chung",
        detail: "Thay đổi người phụ trách đã được ghi vào nhật ký kiểm toán.",
      });
    } catch (cause) {
      pushToast({
        tone: "error",
        title: "Không đổi được người phụ trách",
        detail: cause instanceof Error ? cause.message : "Lỗi không xác định",
      });
    } finally {
      setBusy(false);
    }
  };

  // Chỉ Chuyên viên nhận vụ. Quản lý chốt hồ sơ do Chuyên viên trình; để họ
  // trong danh sách này là mời người phê duyệt vào vị trí người lập hồ sơ.
  const candidates = (team.data?.rows ?? []).filter((r) => r.active && r.role === "analyst");

  return (
    <div className="flex flex-col gap-1.5 border-t border-line-soft pt-2">
      <div className="flex items-center justify-between gap-2">
        <dt className="text-ink-mid">Phụ trách</dt>
        <dd className="font-medium text-ink-hi">{assignedName ?? "Chưa giao"}</dd>
      </div>

      {!closed && (
        <div className="flex flex-wrap gap-1.5">
          {!isManager && assignedTo == null && (
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(currentUser?.id ?? null, "Chuyên viên tự nhận vụ")}
              className="rounded-control border border-line px-2 py-1 text-2xs font-medium text-ink-hi hover:border-line-emphasis disabled:opacity-50"
            >
              Nhận vụ này
            </button>
          )}
          {!isManager && isMine && (
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(null, "Chuyên viên trả vụ về hàng đợi chung")}
              className="rounded-control border border-line px-2 py-1 text-2xs font-medium text-ink-mid hover:text-ink-hi disabled:opacity-50"
            >
              Trả lại hàng đợi
            </button>
          )}
          {isManager && (
            <button
              type="button"
              disabled={busy}
              onClick={() => setPicking((v) => !v)}
              className="rounded-control border border-line px-2 py-1 text-2xs font-medium text-ink-hi hover:border-line-emphasis disabled:opacity-50"
            >
              {assignedTo ? "Đổi người phụ trách" : "Giao cho…"}
            </button>
          )}
          {isManager && assignedTo && (
            <button
              type="button"
              disabled={busy}
              onClick={() => apply(null, "Quản lý thu hồi vụ việc")}
              className="rounded-control border border-line px-2 py-1 text-2xs font-medium text-ink-mid hover:text-ink-hi disabled:opacity-50"
            >
              Thu hồi
            </button>
          )}
        </div>
      )}

      {picking && (
        <ul className="mt-1 space-y-1 rounded-control border border-line bg-elev p-1.5">
          {candidates.length === 0 && <li className="px-1 text-2xs text-ink-low">Đang tải danh sách…</li>}
          {candidates.map((person) => (
            <li key={person.user_id}>
              <button
                type="button"
                disabled={busy || person.user_id === assignedTo}
                onClick={() => apply(person.user_id, `Quản lý giao vụ cho ${person.name}`)}
                className="flex w-full items-center gap-2 rounded-control px-1.5 py-1 text-left text-2xs hover:bg-panel disabled:opacity-40"
              >
                <span className="flex-1 text-ink-hi">{person.name}</span>
                <span className="text-ink-low">{person.role_label}</span>
                <span className="tabular font-mono text-ink-mid">{person.open_cases} vụ</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
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
