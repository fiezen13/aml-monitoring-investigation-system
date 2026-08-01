import {
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  CheckCheck,
  Flag,
  Info,
  Network,
  RefreshCw,
  TrendingUp,
} from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { ReasonModal } from "../components/common/ReasonModal";
import { ScreeningResultCard } from "../components/common/ScreeningResultCard";
import { EmptyState } from "../components/common/States";
import { Tabs } from "../components/common/Tabs";
import { AuditTimeline } from "../components/common/AuditTimeline";
import { EvidenceChip } from "../components/evidence/EvidenceChip";
import { EvidenceDrawer } from "../components/evidence/EvidenceDrawer";
import { DataTable, type Column } from "../components/tables/DataTable";
import { useApp } from "../context/AppContext";
import { ALERT_TRANSACTIONS, SCREENING_RESULTS, getAlert } from "../data/mockAlerts";
import { AUDIT_EVENTS } from "../data/mockAudit";
import { formatUsd } from "../utils/format";
import type { Transaction } from "../types";

const TABS = [
  { id: "overview", label: "Tổng quan" },
  { id: "transactions", label: "Giao dịch" },
  { id: "network", label: "Mạng lưới" },
  { id: "pep", label: "Đối chiếu PEP" },
  { id: "evidence", label: "Bằng chứng" },
  { id: "audit", label: "Audit" },
];

const RISK_TONE: Record<Transaction["riskLevel"], "risk" | "warn" | "ok"> = {
  high: "risk",
  medium: "warn",
  low: "ok",
};

export function AlertDetailPage() {
  const { alertId } = useParams();
  const navigate = useNavigate();
  const { pushToast, caseCreated, createCase } = useApp();
  const alert = getAlert(alertId ?? "");
  const [tab, setTab] = useState("overview");
  const [drawerEvidence, setDrawerEvidence] = useState<string | null>(null);
  const [closeOpen, setCloseOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  if (!alert) {
    return (
      <EmptyState
        title="Không tìm thấy cảnh báo"
        detail={`Cảnh báo "${alertId}" không tồn tại trong hàng đợi.`}
      />
    );
  }

  const isMain = alert.alert_id === "ALT-2026-001";
  const caseReady = isMain && caseCreated;

  const txColumns: Column<Transaction>[] = [
    {
      key: "id",
      header: "Mã Giao dịch",
      render: (t) => <span className="tabular font-medium text-ink-hi">{t.transaction_id}</span>,
    },
    { key: "channel", header: "Kênh", render: (t) => <span className="text-ink-mid">{t.channel}</span> },
    {
      key: "amount",
      header: "Số tiền",
      render: (t) => (
        <span className="tabular">
          {t.currency === "USD" ? `$${formatUsd(t.amount)}` : `${t.amount.toLocaleString("vi-VN")} ₫`}
        </span>
      ),
    },
    {
      key: "risk",
      header: "Loại rủi ro",
      render: (t) => <StatusBadge tone={RISK_TONE[t.riskLevel]} label={t.riskLabel} />,
    },
    {
      key: "status",
      header: "Trạng thái",
      render: () => <span className="text-ink-low">›</span>,
      className: "text-right",
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      {/* Header trang */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/alerts")}
          aria-label="Quay lại hàng đợi"
          className="rounded p-1.5 text-ink-mid hover:bg-panel hover:text-ink-hi"
        >
          <ArrowLeft size={16} />
        </button>
        <h1 className="text-[17px] font-bold text-ink-hi">
          Chi tiết Cảnh báo {alert.alert_id}
        </h1>
        <span className="tabular rounded-control bg-risk px-2 py-1 text-2xs font-bold text-white">
          MỨC ĐỘ RỦI RO {alert.risk_score}
        </span>
        <span className="tabular rounded-control border border-primary/40 bg-primary-soft px-2 py-1 text-2xs font-bold text-primary">
          ĐỘ TIN CẬY AI {alert.ai_confidence}%
        </span>
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={() => setCloseOpen(true)}
            className="rounded-control border border-line px-3 py-1.5 text-[13px] font-medium text-ink-hi hover:border-risk/50 hover:text-risk"
          >
            Đóng cảnh báo
          </button>
          {caseReady ? (
            <button
              type="button"
              onClick={() => navigate("/cases/CASE-2026-014")}
              className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-[13px] font-semibold text-app hover:bg-primary-hover"
            >
              <CheckCheck size={14} aria-hidden />
              Mở vụ việc CASE-2026-014
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-control bg-primary px-3 py-1.5 text-[13px] font-semibold text-app hover:bg-primary-hover"
            >
              <CheckCheck size={14} aria-hidden />
              Tạo vụ việc CASE-2026-014
            </button>
          )}
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      <div className="mt-3 grid gap-3 xl:grid-cols-[1fr_300px]">
        {/* Cột trái */}
        <div className="space-y-3">
          {tab === "overview" && (
            <>
              <Panel
                title={
                  <span className="inline-flex items-center gap-1.5">
                    <TrendingUp size={13} className="text-primary" aria-hidden />
                    Tóm tắt hỗ trợ điều tra
                  </span>
                }
                action={
                  <span className="inline-flex items-center gap-1.5 text-2xs text-ink-low">
                    Cập nhật: 2 phút trước
                    <RefreshCw size={11} aria-hidden />
                  </span>
                }
              >
                <p className="text-[13px] leading-relaxed text-ink-mid">
                  Hệ thống ghi nhận mức độ nghi vấn cao với hành vi{" "}
                  <span className="font-semibold text-risk">
                    phát tán giao dịch (Structuring)
                  </span>{" "}
                  qua 5 tài khoản phụ trong 48 giờ. {alert.summary} Typology được gợi ý:{" "}
                  <span className="font-semibold text-ink-hi">
                    {alert.typology_label} ({alert.typology_code})
                  </span>{" "}
                  — cần con người rà soát trước khi kết luận.
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {alert.evidenceIds.map((id) => (
                    <EvidenceChip key={id} evidenceId={id} onOpen={setDrawerEvidence} />
                  ))}
                </div>
                <div className="mt-4 border-t border-line pt-3">
                  <div className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">
                    Yếu tố đóng góp (NT7 — tối thiểu 3 yếu tố định lượng)
                  </div>
                  <div className="space-y-2">
                    {alert.factors.map((f) => (
                      <div key={f.factor_code} className="flex items-center gap-3">
                        <span className="tabular w-16 shrink-0 text-2xs text-ink-low">
                          {f.factor_code}
                        </span>
                        <span className="flex-1 text-2xs text-ink-mid">{f.factor_label}</span>
                        <span className="text-2xs text-ink-low">{f.detector}</span>
                        <div className="h-1.5 w-24 overflow-hidden rounded bg-elev">
                          <div
                            className="h-full rounded bg-primary"
                            style={{ width: `${f.contribution * 2}%` }}
                          />
                        </div>
                        <span className="tabular w-10 text-right text-2xs font-semibold text-ink-hi">
                          +{f.contribution}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </Panel>

              <div className="grid gap-3 md:grid-cols-2">
                <Panel
                  title={
                    <span className="inline-flex items-center gap-1.5">
                      <Network size={13} aria-hidden />
                      Mạng lưới liên kết
                    </span>
                  }
                >
                  <div className="flex h-36 flex-col items-center justify-center gap-2 rounded-control border border-line bg-elev">
                    <span className="text-[13px] font-semibold text-ink-hi">
                      3 Kết nối rủi ro cao
                    </span>
                    <button
                      type="button"
                      onClick={() => navigate("/network/CASE-2026-014")}
                      className="text-2xs font-medium text-primary hover:underline"
                    >
                      Phóng to biểu đồ
                    </button>
                  </div>
                </Panel>
                <Panel
                  title={
                    <span className="inline-flex items-center gap-1.5">
                      <TrendingUp size={13} aria-hidden />
                      Tiến trình giao dịch
                    </span>
                  }
                >
                  <div className="space-y-2">
                    {ALERT_TRANSACTIONS.slice(0, 2).map((t) => (
                      <div
                        key={t.transaction_id}
                        className="flex items-center gap-2.5 rounded-control border border-line bg-elev px-3 py-2"
                      >
                        <span
                          className={`flex h-6 w-6 items-center justify-center rounded-full ${
                            t.direction === "in" ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn"
                          }`}
                        >
                          {t.direction === "in" ? (
                            <ArrowDownLeft size={12} aria-hidden />
                          ) : (
                            <ArrowUpRight size={12} aria-hidden />
                          )}
                        </span>
                        <div>
                          <div className="tabular text-[13px] font-semibold text-ink-hi">
                            ${formatUsd(t.amount)} - {t.behaviour}
                          </div>
                          <div className="tabular text-2xs text-ink-low">{t.date}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </Panel>
              </div>

              <Panel
                title="CHI TIẾT CÁC GIAO DỊCH NGHI VẤN"
                padded={false}
                action={
                  <button
                    type="button"
                    onClick={() => setTab("transactions")}
                    className="text-2xs font-medium text-primary hover:underline"
                  >
                    Xem tất cả
                  </button>
                }
              >
                <DataTable
                  columns={txColumns}
                  rows={ALERT_TRANSACTIONS.slice(0, 3)}
                  rowKey={(t) => t.transaction_id}
                  dense
                />
              </Panel>
            </>
          )}

          {tab === "transactions" && (
            <Panel title="Toàn bộ giao dịch liên quan" padded={false}>
              <DataTable
                columns={txColumns}
                rows={ALERT_TRANSACTIONS}
                rowKey={(t) => t.transaction_id}
              />
            </Panel>
          )}

          {tab === "network" && (
            <Panel title="Mạng lưới giao dịch">
              <p className="mb-3 text-[13px] text-ink-mid">
                Sơ đồ mạng lưới đầy đủ (GRAPH-008) được phân tích bởi Network Analysis Tool.
              </p>
              <button
                type="button"
                onClick={() => navigate("/network/CASE-2026-014")}
                className="rounded-control bg-primary px-3 py-2 text-[13px] font-semibold text-app hover:bg-primary-hover"
              >
                Mở màn hình Mạng lưới Giao dịch
              </button>
            </Panel>
          )}

          {tab === "pep" && (
            <div className="space-y-3">
              {SCREENING_RESULTS.map((r) => (
                <ScreeningResultCard key={r.id} result={r} />
              ))}
            </div>
          )}

          {tab === "evidence" && (
            <Panel title="Bằng chứng đã gắn">
              {alert.evidenceIds.length === 0 ? (
                <EmptyState detail="Cảnh báo này chưa có bằng chứng nào được gắn." />
              ) : (
                <div className="flex flex-wrap gap-2">
                  {alert.evidenceIds.map((id) => (
                    <EvidenceChip key={id} evidenceId={id} onOpen={setDrawerEvidence} />
                  ))}
                </div>
              )}
            </Panel>
          )}

          {tab === "audit" && (
            <Panel title="Audit trail của cảnh báo (chỉ đọc)">
              <AuditTimeline
                events={AUDIT_EVENTS.filter(
                  (e) => e.target.includes("CASE-2026-014") || e.target.includes("ALT-2026"),
                )}
              />
            </Panel>
          )}
        </div>

        {/* Cột phải: hồ sơ khách hàng */}
        <div className="space-y-3">
          <Panel>
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-panel bg-elev text-[15px] font-bold text-primary">
                {alert.customer.initials}
              </span>
              <div>
                <div className="text-[15px] font-bold text-ink-hi">{alert.customer.name}</div>
                <div className="tabular text-2xs text-ink-low">
                  {alert.customer.customerId} · {alert.customer.accountKey}
                </div>
              </div>
            </div>
            <div className="mt-2.5 flex gap-1.5">
              {alert.customer.pepLevel !== null && (
                <StatusBadge tone="warn" label={`PEP LEVEL ${alert.customer.pepLevel}`} />
              )}
              {alert.customer.kycValid && <StatusBadge tone="ok" label="KYC VALID" />}
            </div>
            <dl className="mt-3 grid grid-cols-2 gap-3 border-t border-line pt-3 text-2xs">
              <div>
                <dt className="uppercase tracking-wide text-ink-low">Quốc tịch</dt>
                <dd className="mt-0.5 font-medium text-ink-hi">{alert.customer.nationality}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-wide text-ink-low">Tuổi hồ sơ</dt>
                <dd className="tabular mt-0.5 font-medium text-ink-hi">
                  {alert.customer.profileAge}
                </dd>
              </div>
              <div className="col-span-2">
                <dt className="uppercase tracking-wide text-ink-low">Lĩnh vực kinh doanh</dt>
                <dd className="mt-0.5 font-medium text-ink-hi">
                  {alert.customer.businessLine}
                </dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Lịch sử cảnh báo">
            <ol className="relative ml-1.5 space-y-4 border-l border-line pl-4">
              <li className="relative">
                <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel bg-risk" aria-hidden />
                <div className="text-2xs font-semibold text-ink-hi">
                  Cảnh báo Hiện tại: {alert.alert_id}
                </div>
                <div className="tabular text-2xs text-ink-low">
                  MAY 19, 2026 · HIGH RISK ({alert.risk_score})
                </div>
                <p className="mt-1 text-2xs italic leading-relaxed text-ink-mid">
                  "Cần xác minh nguồn gốc dòng tiền từ các tài khoản trung gian."
                </p>
              </li>
              <li className="relative">
                <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel bg-ink-low" aria-hidden />
                <div className="text-2xs font-semibold text-ink-mid">Lịch sử: ALT-2024-552</div>
                <div className="tabular text-2xs text-ink-low">DEC 12, 2025 · LOW RISK (15)</div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-mid">
                  Hành vi rút tiền ATM bất thường ban đêm. Đã đóng (Benign).
                </p>
              </li>
              <li className="relative">
                <span className="absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel bg-ink-low" aria-hidden />
                <div className="text-2xs font-semibold text-ink-mid">Lịch sử: ALT-2023-110</div>
                <div className="tabular text-2xs text-ink-low">
                  JUN 05, 2024 · MEDIUM RISK (42)
                </div>
              </li>
            </ol>
          </Panel>

          <Panel elevated>
            <div className="flex items-center gap-1.5 text-[13px] font-semibold text-info">
              <Info size={13} aria-hidden />
              Khuyến nghị từ AI
            </div>
            <p className="mt-1.5 text-2xs leading-relaxed text-ink-mid">
              Dựa trên lịch sử, khách hàng thường xuyên thực hiện các giao dịch dưới ngưỡng
              báo cáo. Đề xuất nâng mức giám sát (Enhanced Due Diligence). Gợi ý điều tra —
              quyết định cuối cùng thuộc về con người.
            </p>
            <button
              type="button"
              onClick={() =>
                pushToast({
                  tone: "success",
                  title: "Đã tải báo cáo phân tích rủi ro (mô phỏng)",
                  detail: "Nguồn: Backend Analytics · CALC-014",
                })
              }
              className="mt-3 w-full rounded-control border border-line py-2 text-[13px] font-medium text-ink-hi hover:border-primary/50"
            >
              Tải báo cáo phân tích rủi ro
            </button>
          </Panel>
        </div>
      </div>

      <EvidenceDrawer
        evidenceId={drawerEvidence}
        onClose={() => setDrawerEvidence(null)}
        onSelect={setDrawerEvidence}
      />

      <ReasonModal
        open={closeOpen}
        title="Đóng cảnh báo không báo cáo"
        description="Cảnh báo sẽ chuyển sang trạng thái DongKhongBaoCao. Lý do là bắt buộc và được ghi bất biến vào audit trail (NT3, NT4)."
        confirmLabel="Đóng cảnh báo"
        minLength={30}
        onClose={() => setCloseOpen(false)}
        onConfirm={() => {
          setCloseOpen(false);
          pushToast({
            tone: "success",
            title: "Đã đóng cảnh báo",
            detail: "Hành động DONG_KHONG_BAO_CAO đã ghi vào audit trail.",
          });
          navigate("/alerts");
        }}
      />

      <ReasonModal
        open={createOpen}
        title={`Tạo vụ việc từ ${alert.alert_id}`}
        description="Vụ việc CASE-2026-014 sẽ được tạo và agent bắt đầu 9 bước điều tra. Lý do là bắt buộc (NT3)."
        confirmLabel="Tạo vụ việc"
        onClose={() => setCreateOpen(false)}
        onConfirm={(reason) => {
          createCase(reason);
          setCreateOpen(false);
          pushToast({
            tone: "success",
            title: "Đã tạo vụ việc CASE-2026-014",
            detail: "Agent bắt đầu truy hồi bằng chứng.",
          });
          navigate("/cases/CASE-2026-014");
        }}
      />

      {!caseReady && (
        <div className="mt-3 flex items-center gap-2 rounded-panel border border-line bg-panel px-3 py-2 text-2xs text-ink-mid">
          <Flag size={12} className="text-ink-low" aria-hidden />
          Không có chức năng phong tỏa tài khoản hay báo cáo tự động tới cơ quan quản lý —
          con người quyết định cuối cùng (NT3).
        </div>
      )}
    </div>
  );
}
