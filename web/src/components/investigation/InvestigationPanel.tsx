import { CheckCircle2, ChevronRight, Play, RefreshCw, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { api } from "../../api/client";
import {
  agentLabel,
  evidenceTypeLabel,
  formatDateTime,
  investigationStatusLabel,
  investigationTextVi,
  recommendedActionLabel,
  riskComponentLabel,
  toolLabel,
  traceEventLabel,
  validationStatusLabel,
  validationIssueLabel,
} from "../../api/format";
import { useApi } from "../../api/useApi";
import { useApp } from "../../context/AppContext";
import { StatusBadge } from "../common/Badges";
import { Panel } from "../common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../common/States";

const ACTIVE = new Set(["QUEUED", "INVESTIGATING"]);
// An investigation that stops for a human still produced the explanation that
// sent it there, and that is the part a reviewer needs to read.
const EXPLAINED = new Set(["COMPLETED", "NEEDS_HUMAN_REVIEW", "INSUFFICIENT_EVIDENCE"]);
const REVIEW_ACTIONS = [
  ["CONTINUE_MONITORING", "Tiếp tục giám sát"],
  ["REQUEST_MORE_INFORMATION", "Yêu cầu thêm thông tin"],
  ["ESCALATE_TO_L2", "Chuyển lên cấp rà soát 2"],
  ["REVIEW_FOR_SAR_STR", "Rà soát để lập báo cáo SAR/STR"],
  ["CLOSE_AS_LIKELY_FALSE_POSITIVE", "Đóng — nhiều khả năng là cảnh báo giả"],
] as const;

export function InvestigationPanel({ alertId }: { alertId: string }) {
  const { pushToast } = useApp();
  const [starting, setStarting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [decision, setDecision] = useState<(typeof REVIEW_ACTIONS)[number][0]>("ESCALATE_TO_L2");
  const [reason, setReason] = useState("");
  const latest = useApi(() => api.latestInvestigation(alertId), [alertId]);
  const investigationId = latest.data?.investigation_id ?? null;
  const evidence = useApi(
    () => (investigationId ? api.investigationEvidence(investigationId) : Promise.resolve([])),
    [investigationId, latest.data?.updated_at],
  );
  const trace = useApi(
    () => (investigationId ? api.investigationTrace(investigationId) : Promise.resolve([])),
    [investigationId, latest.data?.updated_at],
  );
  const explanation = useApi(
    () =>
      investigationId && EXPLAINED.has(latest.data?.status ?? "")
        ? api.investigationExplanation(investigationId)
        : Promise.resolve(null),
    [investigationId, latest.data?.status],
  );

  useEffect(() => {
    if (!latest.data || !ACTIVE.has(latest.data.status)) return;
    const timer = window.setInterval(latest.reload, 2000);
    return () => window.clearInterval(timer);
  }, [latest.data, latest.reload]);

  async function start() {
    setStarting(true);
    try {
      const result = await api.investigateAlert(alertId);
      pushToast({ tone: "success", title: `Đã giao tác vụ ${result.job_id}` });
      latest.reload();
    } catch (error) {
      pushToast({ tone: "error", title: error instanceof Error ? error.message : "Không khởi động được" });
    } finally {
      setStarting(false);
    }
  }

  async function review() {
    if (!investigationId || reason.trim().length < 10) {
      pushToast({ tone: "info", title: "Lý do rà soát cần ít nhất 10 ký tự" });
      return;
    }
    setReviewing(true);
    try {
      await api.reviewInvestigation(investigationId, decision, reason.trim());
      pushToast({ tone: "success", title: "Đã lưu quyết định của chuyên viên" });
      latest.reload();
    } catch (error) {
      pushToast({ tone: "error", title: error instanceof Error ? error.message : "Không lưu được kết quả rà soát" });
    } finally {
      setReviewing(false);
    }
  }

  if (latest.loading) return <LoadingSkeleton rows={5} />;
  if (latest.error) return <ErrorState detail={latest.error} onRetry={latest.reload} />;
  if (!latest.data) {
    return (
      <Panel title="Điều tra đa tác tử có thể giải thích">
        <EmptyState
          title="Chưa có phiên điều tra"
          detail="Khởi động Tác tử điều phối → Tác tử giải thích → Tác tử phản biện bằng chứng. Quy trình chạy nền và không tự thực hiện quyết định nghiệp vụ."
        />
        <button
          type="button"
          disabled={starting}
          onClick={start}
          className="mx-auto mt-3 flex items-center gap-1.5 rounded-control bg-primary px-4 py-2 text-2xs font-semibold text-app disabled:opacity-50"
        >
          <Play size={13} /> {starting ? "Đang giao tác vụ…" : "Bắt đầu điều tra"}
        </button>
      </Panel>
    );
  }

  const inv = latest.data;
  const risk = inv.risk_summary;
  return (
    <div className="space-y-3">
      <Panel
        title="Trạng thái điều tra"
        action={
          <button type="button" onClick={latest.reload} className="text-ink-mid hover:text-ink-hi" aria-label="Làm mới">
            <RefreshCw size={13} />
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            tone={inv.status === "COMPLETED" ? "ok" : inv.status === "FAILED" ? "risk" : "primary"}
            label={investigationStatusLabel(inv.status)}
          />
          <span className="tabular text-2xs text-ink-mid">{inv.investigation_id}</span>
          <span className="text-2xs text-ink-low">
            vòng lặp {inv.iteration} · {inv.tool_call_count} lần gọi công cụ · ảnh chụp dữ liệu {formatDateTime(inv.snapshot_time)}
          </span>
        </div>
        {inv.failure_reason && <p className="mt-2 text-2xs text-risk">{investigationTextVi(inv.failure_reason)}</p>}
        <p className="mt-2 text-2xs text-ink-low">
          Không lưu chuỗi suy luận nội bộ. Dòng thời gian bên dưới chỉ gồm quyết định ngắn, công cụ và mã tham chiếu bằng chứng.
        </p>
      </Panel>

      {risk.components && (
        <Panel title="Chi tiết điểm rủi ro">
          <div className="mb-3 flex items-baseline gap-2">
            <span className="tabular text-2xl font-bold text-ink-hi">
              {Math.round((risk.final_risk_score ?? 0) * 100)}
            </span>
            <span className="text-2xs text-ink-mid">rủi ro cuối cùng · nguồn: Bộ máy phát hiện</span>
          </div>
          <div className="space-y-2">
            {Object.entries(risk.components).map(([name, component]) => (
              <div key={name} className={component.available ? "" : "opacity-40"}>
                <div className="mb-1 flex justify-between text-2xs">
                  <span className="capitalize text-ink-hi">{riskComponentLabel(name)}</span>
                  <span className="tabular text-ink-mid">
                    điểm {component.score.toFixed(3)} · trọng số {component.weight.toFixed(2)} · mức đóng góp {component.contribution.toFixed(3)}
                  </span>
                </div>
                <div className="h-1.5 rounded bg-elev">
                  <div className="h-full rounded bg-primary" style={{ width: `${component.score * 100}%` }} />
                </div>
              </div>
            ))}
          </div>
          {!risk.fusion_available && risk.limitation && (
            <p className="mt-3 border-t border-line pt-2 text-2xs text-ink-low">{risk.limitation}</p>
          )}
        </Panel>
      )}

      {explanation.data && (
        <Panel title="Vì sao cảnh báo này được tạo?">
          {inv.status !== "COMPLETED" && (
            <p className="mb-3 rounded-control border border-warn/30 bg-warn/10 p-2 text-2xs text-warn-soft">
              Bản giải thích này chưa vượt qua bước phản biện bằng chứng. Xem phần Tác tử phản biện bằng chứng bên dưới
              để biết vấn đề còn lại trước khi sử dụng.
            </p>
          )}
          <p className="text-body leading-relaxed text-ink-hi">{investigationTextVi(explanation.data.summary)}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <ExplanationList title="DỮ KIỆN" items={explanation.data.claims.filter((claim) => claim.claim_type === "FACT")} />
            <ExplanationList title="SUY LUẬN" items={explanation.data.claims.filter((claim) => claim.claim_type === "INFERENCE")} />
            <TextList title="THÔNG TIN CÒN THIẾU" items={explanation.data.missing_information} />
            <div>
              <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">BƯỚC TIẾP THEO ĐƯỢC ĐỀ XUẤT</h4>
              <p className="text-body text-ink-hi">{recommendedActionLabel(explanation.data.recommended_action)}</p>
              <p className="mt-1 text-2xs text-warn">Bắt buộc chuyên viên rà soát — không tự động thực hiện quyết định nghiệp vụ.</p>
            </div>
          </div>
        </Panel>
      )}

      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title={`Bằng chứng (${evidence.data?.length ?? 0})`}>
          {evidence.loading ? (
            <LoadingSkeleton rows={3} />
          ) : (
            <div className="space-y-2">
              {(evidence.data ?? []).map((item) => (
                <details key={item.evidence_id} className="rounded-control border border-line bg-elev p-2.5">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-2xs text-ink-hi">
                    <ChevronRight size={12} />
                    <span className="font-semibold">{evidenceTypeLabel(item.type)}</span>
                    <span className="tabular ml-auto text-ink-low">{item.evidence_id}</span>
                  </summary>
                  <div className="mt-2 border-t border-line pt-2 text-2xs text-ink-mid">
                    <div>Nguồn: {item.source}</div>
                    <div className="mt-1 break-all">SHA-256: {item.integrity.content_hash}</div>
                    <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded bg-app p-2 text-micro text-ink-mid">
                      {JSON.stringify(item.payload, null, 2)}
                    </pre>
                  </div>
                </details>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Dòng thời gian tác tử">
          <ol className="space-y-3">
            {(trace.data ?? []).map((event) => (
              <li key={event.trace_id} className="flex gap-2 text-2xs">
                {event.event_type === "VALIDATION_PASS" ? (
                  <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-ok" />
                ) : event.event_type === "CRITIC_OBJECTION_REFUTED" ? (
                  // Không phải kết quả kiểm chứng — chỉ là loại bớt khiếu nại sai.
                  // Dùng dấu riêng để không ai đọc nhầm thành "đã đạt".
                  <ShieldCheck size={13} className="mt-0.5 shrink-0 text-info" />
                ) : event.event_type === "VALIDATION_FAIL" || event.event_type === "INVESTIGATION_FAILED" ? (
                  <XCircle size={13} className="mt-0.5 shrink-0 text-risk" />
                ) : (
                  <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary" />
                )}
                <div>
                  <div className="font-semibold text-ink-hi">{traceEventLabel(event.event_type)}</div>
                  <div className="text-ink-mid">{investigationTextVi(event.short_rationale)}</div>
                  <div className="tabular text-ink-low">
                    {formatDateTime(event.occurred_at)} · {agentLabel(event.agent)}
                    {event.tool ? ` · ${toolLabel(event.tool)}` : ""}
                    {event.output_ref ? ` · ${event.output_ref}` : ""}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </Panel>
      </div>

      {inv.validation && (
        <Panel title="Tác tử phản biện bằng chứng">
          <div className="flex items-center gap-2">
            {inv.validation.status === "PASS" ? <CheckCircle2 className="text-ok" size={18} /> : <ShieldAlert className="text-risk" size={18} />}
            <span className="font-semibold text-ink-hi">{validationStatusLabel(inv.validation.status)}</span>
            <span className="tabular text-2xs text-ink-mid">độ tin cậy {inv.validation.confidence.toFixed(2)}</span>
          </div>
          {inv.validation.issues.map((issue, index) => (
            <div key={`${issue.type}-${index}`} className="mt-2 rounded-control border border-risk/30 bg-risk-soft p-2 text-2xs text-ink-hi">
              <strong>{validationIssueLabel(issue.type)}</strong> — {investigationTextVi(issue.detail)}
            </div>
          ))}
        </Panel>
      )}

      {["COMPLETED", "INSUFFICIENT_EVIDENCE", "NEEDS_HUMAN_REVIEW"].includes(inv.status) && (
        <Panel title="Chuyên viên phân tích rà soát">
          {inv.human_review ? (
            <div className="rounded-control border border-ok/30 bg-ok-soft p-3 text-2xs text-ink-hi">
              Quyết định đã được ghi vào nhật ký kiểm toán: {recommendedActionLabel(String(inv.human_review.decision))}
            </div>
          ) : (
            <div className="grid gap-2 md:grid-cols-[220px_1fr_auto]">
              <select value={decision} onChange={(event) => setDecision(event.target.value as typeof decision)} className="rounded-control border border-line bg-elev px-2 py-2 text-2xs text-ink-hi">
                {REVIEW_ACTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
              <input value={reason} onChange={(event) => setReason(event.target.value)} placeholder="Lý do nghiệp vụ (bắt buộc)" className="rounded-control border border-line bg-elev px-3 py-2 text-2xs text-ink-hi" />
              <button type="button" onClick={review} disabled={reviewing} className="rounded-control bg-primary px-4 py-2 text-2xs font-semibold text-app disabled:opacity-50">
                {reviewing ? "Đang lưu…" : "Lưu kết quả rà soát"}
              </button>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

function ExplanationList({ title, items }: { title: string; items: Array<{ claim_id: string; claim: string; evidence_refs: string[] }> }) {
  return (
    <div>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{title}</h4>
      {items.length === 0 ? <p className="text-2xs text-ink-low">Không có.</p> : (
        <ul className="space-y-2">
          {items.map((item) => <li key={item.claim_id} className="text-body text-ink-hi">{investigationTextVi(item.claim)}<div className="tabular text-2xs text-info">{item.evidence_refs.join(" · ")}</div></li>)}
        </ul>
      )}
    </div>
  );
}

function TextList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{title}</h4>
      {items.length === 0 ? <p className="text-2xs text-ink-low">Không có.</p> : <ul className="space-y-1 text-body text-ink-hi">{items.map((item) => <li key={item}>• {investigationTextVi(item)}</li>)}</ul>}
    </div>
  );
}
