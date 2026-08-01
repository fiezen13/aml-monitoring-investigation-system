import { FileEdit, Network, UserRound } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { AgentTimeline } from "../components/common/AgentTimeline";
import { StatusBadge } from "../components/common/Badges";
import { Panel } from "../components/common/Panel";
import { EmptyState } from "../components/common/States";
import { Tabs } from "../components/common/Tabs";
import { Breadcrumb } from "../components/layout/Breadcrumb";
import { EvidenceChip } from "../components/evidence/EvidenceChip";
import { EvidenceDrawer } from "../components/evidence/EvidenceDrawer";
import { DataTable, type Column } from "../components/tables/DataTable";
import { getCase } from "../data/mockCases";
import type { FlowAnalysisRow } from "../types";

const TABS = [
  { id: "flow", label: "Transaction Analysis" },
  { id: "link", label: "Link Analysis" },
  { id: "history", label: "Risk Score History" },
];

/** Hồ sơ vụ việc — bám screenshot CASE-2026-014 với Evidence Drawer bên phải. */
export function CaseDetailPage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const amlCase = getCase(caseId ?? "");
  const [tab, setTab] = useState("flow");
  const [drawerEvidence, setDrawerEvidence] = useState<string | null>(
    amlCase?.case_id === "CASE-2026-014" ? "EV-00031" : null,
  );

  if (!amlCase) {
    return (
      <EmptyState
        title="Không tìm thấy vụ việc"
        detail={`Vụ việc "${caseId}" không tồn tại.`}
      />
    );
  }

  const flowColumns: Column<FlowAnalysisRow>[] = [
    {
      key: "date",
      header: "Ngày giao dịch",
      render: (r) => <span className="tabular text-ink-mid">{r.date}</span>,
    },
    {
      key: "tx",
      header: "Mã giao dịch",
      render: (r) => <span className="tabular font-medium text-info">{r.transaction_id}</span>,
    },
    {
      key: "behaviour",
      header: "Hành vi",
      render: (r) => (
        <StatusBadge
          tone={r.behaviourTone}
          label={r.behaviour}
        />
      ),
    },
  ];

  return (
    <div className="mx-auto max-w-[1280px]">
      <Breadcrumb
        items={[
          { label: "Hồ sơ vụ việc", to: "/cases" },
          { label: amlCase.case_id },
        ]}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h1 className="text-[18px] font-bold text-ink-hi">
          {amlCase.case_id}: {amlCase.title}
        </h1>
        <StatusBadge tone="warn" label="ĐANG ĐIỀU TRA" />
      </div>

      <div className="grid gap-3 xl:grid-cols-[260px_1fr]">
        {/* Cột trái: luồng xử lý + khách hàng liên quan */}
        <div className="space-y-3">
          <Panel title="Luồng xử lý hồ sơ">
            <AgentTimeline steps={amlCase.timeline} />
          </Panel>

          <Panel
            title={
              <span className="inline-flex items-center gap-1.5">
                <UserRound size={13} aria-hidden />
                Khách hàng liên quan
              </span>
            }
          >
            <div className="rounded-control border border-line bg-elev p-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-panel text-2xs font-bold text-primary">
                  {amlCase.customer.initials}
                </span>
                <div>
                  <div className="text-[13px] font-bold uppercase text-ink-hi">
                    {amlCase.customer.name}
                  </div>
                  <div className="tabular text-2xs text-ink-low">
                    CID: {amlCase.customer.customerId}
                  </div>
                  <div className="mt-0.5">
                    <StatusBadge tone="risk" label={`RỦI RO CAO (${amlCase.risk_score})`} />
                  </div>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-2 border-t border-line pt-2.5 text-2xs">
                <div>
                  <dt className="uppercase text-ink-low">Loại KH</dt>
                  <dd className="mt-0.5 font-medium text-ink-hi">{amlCase.customer.segment}</dd>
                </div>
                <div>
                  <dt className="uppercase text-ink-low">Quốc tịch</dt>
                  <dd className="mt-0.5 font-medium text-ink-hi">
                    {amlCase.customer.nationality}
                  </dd>
                </div>
              </dl>
            </div>
          </Panel>

          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => navigate(`/network/${amlCase.case_id}`)}
              className="inline-flex items-center justify-center gap-1.5 rounded-control border border-line bg-panel py-2 text-2xs font-semibold text-ink-hi hover:border-primary/50"
            >
              <Network size={12} aria-hidden />
              Xem mạng lưới
            </button>
            <button
              type="button"
              disabled={!amlCase.sarId}
              title={amlCase.sarId ? undefined : "Vụ việc chưa có bản nháp SAR"}
              onClick={() => amlCase.sarId && navigate(`/sar/${amlCase.sarId}/edit`)}
              className="inline-flex items-center justify-center gap-1.5 rounded-control bg-primary py-2 text-2xs font-semibold text-app hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              <FileEdit size={12} aria-hidden />
              Mở bản nháp SAR
            </button>
          </div>
        </div>

        {/* Cột giữa: phân tích dòng tiền */}
        <div className="space-y-3">
          <Panel padded={false}>
            <div className="px-4 pt-3">
              <Tabs tabs={TABS} active={tab} onChange={setTab} />
            </div>
            {tab === "flow" && (
              <div>
                <div className="px-4 py-3">
                  <div className="text-[14px] font-semibold text-ink-hi">
                    Biểu đồ dòng tiền (Flow Analysis)
                  </div>
                  <p className="mt-0.5 text-2xs text-ink-mid">
                    Phân tích các giao dịch dưới ngưỡng báo cáo trong vòng 30 ngày.
                  </p>
                </div>
                {amlCase.flowRows.length === 0 ? (
                  <EmptyState detail="Vụ việc này chưa có dữ liệu phân tích dòng tiền." />
                ) : (
                  <DataTable
                    columns={flowColumns}
                    rows={amlCase.flowRows}
                    rowKey={(r) => r.transaction_id}
                    dense
                  />
                )}
              </div>
            )}
            {tab === "link" && (
              <div className="p-4">
                <p className="mb-3 text-[13px] text-ink-mid">
                  Phân tích liên kết được thực hiện bởi Network Analysis Tool (GRAPH-008).
                </p>
                <button
                  type="button"
                  onClick={() => navigate(`/network/${amlCase.case_id}`)}
                  className="rounded-control bg-primary px-3 py-2 text-[13px] font-semibold text-app hover:bg-primary-hover"
                >
                  Mở sơ đồ mạng lưới đầy đủ
                </button>
              </div>
            )}
            {tab === "history" && (
              <div className="p-4">
                <div className="space-y-2">
                  {[
                    { date: "12/05/2026", score: 89, note: "Sau khi gắn EV-00052 (CALC-014)" },
                    { date: "11/05/2026", score: 74, note: "Phát hiện chuỗi giao dịch dưới ngưỡng" },
                    { date: "10/05/2026", score: 41, note: "Điểm khởi tạo từ cảnh báo" },
                  ].map((h) => (
                    <div
                      key={h.date}
                      className="flex items-center gap-3 rounded-control border border-line bg-elev px-3 py-2"
                    >
                      <span className="tabular w-20 text-2xs text-ink-low">{h.date}</span>
                      <span className="tabular w-10 text-[14px] font-bold text-ink-hi">
                        {h.score}
                      </span>
                      <span className="flex-1 text-2xs text-ink-mid">{h.note}</span>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-2xs text-ink-low">
                  Nguồn điểm: Công cụ tính toán CALC-014 — không phải số do mô hình tự sinh (NT2).
                </p>
              </div>
            )}
          </Panel>

          <Panel title="Bằng chứng trong case" >
            <div className="flex flex-wrap gap-1.5">
              {["EV-00031", "EV-00045", "EV-00052", "EV-00029", "EV-00030"].map((id) => (
                <EvidenceChip key={id} evidenceId={id} onOpen={setDrawerEvidence} />
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <EvidenceDrawer
        evidenceId={drawerEvidence}
        onClose={() => setDrawerEvidence(null)}
        onSelect={setDrawerEvidence}
      />
    </div>
  );
}
