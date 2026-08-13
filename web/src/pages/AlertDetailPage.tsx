import {
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  FolderSearch,
  Info,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api, num } from "../api/client";
import {
  alertStatusLabel,
  caseStateLabel,
  countryLabel,
  detectorLabel,
  formatAmount,
  formatDate,
  formatDateTime,
  initials,
  profileValueLabel,
  prototypeLabel,
  riskRatingLabel,
} from "../api/format";
import { useApi } from "../api/useApi";
import { RiskBadge, StatusBadge } from "../components/common/Badges";
import { AuditFeed } from "../components/common/AuditFeed";
import { Panel } from "../components/common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../components/common/States";
import { Tabs } from "../components/common/Tabs";
import { InvestigationPanel } from "../components/investigation/InvestigationPanel";
import { DataTable, type Column } from "../components/tables/DataTable";
import type { ApiTransaction } from "../api/client";

const TABS = [
  { id: "overview", label: "Tổng quan" },
  { id: "transactions", label: "Giao dịch" },
  { id: "audit", label: "Nhật ký" },
  { id: "investigation", label: "Điều tra bằng AI" },
];

const DETECTOR_TONE: Record<string, "info" | "primary" | "muted"> = {
  rule: "muted",
  ml: "primary",
  graph: "info",
};

const RISK_RATING_TONE: Record<string, "risk" | "warn" | "ok"> = {
  high: "risk",
  medium: "warn",
  low: "ok",
};

export function AlertDetailPage() {
  const { alertId } = useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");

  const alert = useApi(() => api.alert(alertId ?? ""), [alertId]);
  const caseId = alert.data?.case_id ?? null;
  const audit = useApi(
    () => (caseId ? api.audit({ case_id: caseId, limit: 50 }) : Promise.resolve([])),
    [caseId],
  );

  if (alert.loading) {
    return (
      <div className="mx-auto max-w-[1280px]">
        <LoadingSkeleton rows={8} />
      </div>
    );
  }

  if (alert.error || !alert.data) {
    return (
      <div className="mx-auto max-w-[1280px]">
        {alert.error?.includes("Không tìm thấy") ? (
          <EmptyState
            title="Không tìm thấy cảnh báo"
            detail={`Cảnh báo "${alertId}" không có trong hàng đợi.`}
          />
        ) : (
          <ErrorState detail={alert.error ?? "Không tải được cảnh báo"} onRetry={alert.reload} />
        )}
      </div>
    );
  }

  const a = alert.data;
  const c = a.customer;
  const score = Math.round(num(a.risk_score));
  const totalContribution = a.reasons.reduce((sum, r) => sum + num(r.contribution), 0);

  const txColumns: Column<ApiTransaction>[] = [
    {
      key: "id",
      header: "Mã giao dịch",
      render: (t) => <span className="tabular font-medium text-info">#{t.transaction_id}</span>,
    },
    {
      key: "time",
      header: "Thời điểm",
      render: (t) => <span className="tabular text-ink-mid">{formatDateTime(t.occurred_at)}</span>,
    },
    {
      key: "direction",
      header: "Chiều",
      render: (t) =>
        t.direction === "in" ? (
          <span className="inline-flex items-center gap-1 text-ok">
            <ArrowDownLeft size={12} aria-hidden />
            Vào
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-warn">
            <ArrowUpRight size={12} aria-hidden />
            Ra
          </span>
        ),
    },
    {
      key: "counterparty",
      header: "Đối tác",
      render: (t) => (
        <span className="tabular text-ink-mid">
          {t.direction === "in" ? t.from_account_key : t.to_account_key}
        </span>
      ),
    },
    {
      key: "amount",
      header: "Số tiền",
      render: (t) => (
        <span className="tabular font-semibold text-ink-hi">{formatAmount(t.amount, t.currency)}</span>
      ),
    },
    { key: "channel", header: "Kênh", render: (t) => <span className="text-ink-mid">{t.channel}</span> },
  ];

  return (
    <div className="mx-auto max-w-[1280px] space-y-3">
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
          <h1 className="tabular text-[20px] font-bold text-ink-hi">{a.alert_id}</h1>
          <p className="mt-0.5 text-[13px] text-ink-mid">
            <span className="tabular font-semibold">{a.typology_code}</span> — {a.typology_label}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            tone={DETECTOR_TONE[a.detector] ?? "muted"}
            label={`Phát hiện: ${detectorLabel(a.detector)}`}
          />
          <StatusBadge tone="muted" label={alertStatusLabel(a.status)} />
          <button
            type="button"
            onClick={alert.reload}
            className="inline-flex items-center gap-1.5 rounded-control border border-line bg-panel px-2.5 py-1.5 text-2xs font-medium text-ink-hi hover:border-line-emphasis"
          >
            <RefreshCw size={12} aria-hidden />
            Làm mới
          </button>
          {a.case_id && (
            <button
              type="button"
              onClick={() => navigate(`/cases/${a.case_id}`)}
              className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-2xs font-semibold text-app hover:bg-primary-hover"
            >
              <FolderSearch size={12} aria-hidden />
              Mở vụ việc {a.case_id}
            </button>
          )}
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" && (
        <div className="grid gap-3 lg:grid-cols-[1fr_320px]">
          <div className="space-y-3">
            <Panel title="Yếu tố đóng góp vào điểm rủi ro">
              <div className="mb-3 flex items-center gap-3 rounded-control border border-line bg-elev px-3 py-2">
                <RiskBadge score={score} />
                <span className="text-2xs text-ink-mid">
                  Tổng đóng góp của {a.reasons.length} yếu tố:{" "}
                  <span className="tabular font-semibold text-ink-hi">{totalContribution.toFixed(2)}</span>
                </span>
              </div>
              {a.reasons.length === 0 ? (
                <EmptyState title="Không có yếu tố" detail="Cảnh báo này chưa ghi yếu tố đóng góp nào." />
              ) : (
                <div className="space-y-3">
                  {a.reasons.map((r) => {
                    const contribution = num(r.contribution);
                    const pct = totalContribution > 0 ? (contribution / totalContribution) * 100 : 0;
                    return (
                      <div key={r.factor_code}>
                        <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-2xs">
                          <span className="text-ink-hi">{r.factor_label}</span>
                          <span className="tabular text-ink-mid">
                            đóng góp{" "}
                            <span className="font-semibold text-ink-hi">{contribution.toFixed(2)}</span>
                            {" · "}trọng số {num(r.weight).toFixed(2)}
                          </span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded bg-elev">
                          <div className="h-full rounded bg-primary" style={{ width: `${pct}%` }} />
                        </div>
                        <div className="tabular mt-0.5 text-2xs text-ink-low">{r.factor_code}</div>
                      </div>
                    );
                  })}
                </div>
              )}
              <div className="mt-4 flex items-start gap-1.5 border-t border-line pt-3 text-2xs text-ink-low">
                <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
                <p>
                  NT7 — mỗi điểm rủi ro luôn kèm danh sách yếu tố đóng góp có giá trị số. Điểm này đến từ bộ
                  luật và heuristic trong dữ liệu mẫu, chưa phải mô hình đã huấn luyện.
                </p>
              </div>
            </Panel>
          </div>

          <div className="space-y-3">
            <Panel title="Hồ sơ chủ thể">
              <div className="mb-3 flex items-center gap-2.5">
                <span className="flex h-10 w-10 items-center justify-center rounded-full bg-elev text-[13px] font-bold text-primary">
                  {initials(c.customer_id)}
                </span>
                <div>
                  <div className="tabular text-[14px] font-semibold text-ink-hi">{c.customer_id}</div>
                  <div className="text-2xs text-ink-mid">{profileValueLabel(c.occupation)}</div>
                </div>
              </div>
              <dl className="space-y-2 text-2xs">
                <Field label="Tài khoản" value={c.account_key} mono />
                <Field label="Ngân hàng" value={c.bank_code} mono />
                <Field
                  label="Loại chủ thể"
                  value={c.customer_type === "organisation" ? "Tổ chức" : "Cá nhân"}
                />
                <Field label="Nguyên mẫu" value={prototypeLabel(c.prototype)} />
                <Field label="Thu nhập khai báo" value={profileValueLabel(c.declared_income_band)} />
                <Field label="Doanh số kỳ vọng/tháng" value={formatAmount(c.expected_monthly_volume)} mono />
                <Field label="Quốc gia đăng ký" value={countryLabel(c.registered_country)} />
                <Field label="Ngày mở hồ sơ" value={formatDate(c.onboarding_date)} />
                <Field label="Trạng thái tài khoản" value={profileValueLabel(c.account_status)} />
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
              <p className="mt-3 border-t border-line pt-2 text-2xs text-ink-low">
                Mức rủi ro hồ sơ suy ra từ nguyên mẫu và quốc gia đăng ký, không suy ra từ nhãn rửa tiền (ND1).
              </p>
            </Panel>

            {a.case_id && (
              <Panel title="Vụ việc liên quan">
                <div className="space-y-1.5 text-2xs">
                  <div className="tabular text-[14px] font-semibold text-info">{a.case_id}</div>
                  {a.case_state && <StatusBadge tone="primary" label={caseStateLabel(a.case_state)} />}
                </div>
                <button
                  type="button"
                  onClick={() => navigate(`/cases/${a.case_id}`)}
                  className="mt-3 w-full rounded-control bg-primary py-2 text-2xs font-semibold text-app transition-colors hover:bg-primary-hover"
                >
                  Mở hồ sơ điều tra →
                </button>
              </Panel>
            )}
          </div>
        </div>
      )}

      {tab === "transactions" && (
        <Panel
          padded={false}
          title={`Giao dịch gần nhất của ${a.account_key}`}
          action={<span className="text-2xs text-ink-low">20 giao dịch mới nhất, cả hai chiều</span>}
        >
          {a.transactions.length === 0 ? (
            <EmptyState detail="Tài khoản này chưa có giao dịch nào." />
          ) : (
            <DataTable columns={txColumns} rows={a.transactions} rowKey={(t) => String(t.transaction_id)} />
          )}
        </Panel>
      )}

      {tab === "audit" && (
        <Panel title="Nhật ký kiểm toán của vụ việc">
          {!a.case_id ? (
            <EmptyState
              title="Chưa gom vào vụ việc"
              detail="Cảnh báo chưa thuộc vụ việc nào nên chưa có nhật ký kiểm toán."
            />
          ) : audit.loading ? (
            <LoadingSkeleton rows={4} />
          ) : audit.error ? (
            <ErrorState detail={audit.error} onRetry={audit.reload} />
          ) : (
            <AuditFeed events={audit.data ?? []} />
          )}
        </Panel>
      )}

      {tab === "investigation" && <InvestigationPanel alertId={a.alert_id} />}
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
