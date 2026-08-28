import { CheckCircle2, ChevronRight, Loader2, Play, RefreshCw, ScanSearch, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import { PERMISSIONS } from "../../rbac/permissions";
import { StatusBadge } from "../common/Badges";
import { EvidenceBody } from "./EvidenceBody";
import { Panel } from "../common/Panel";
import { EmptyState, ErrorState, LoadingSkeleton } from "../common/States";

const ACTIVE = new Set(["QUEUED", "INVESTIGATING"]);
/** Nhịp hỏi lại khi tác tử đang chạy. Một phiên mất khoảng 40–90 giây. */
const POLL_MS = 2000;
// An investigation that stops for a human still produced the explanation that
// sent it there, and that is the part a reviewer needs to read.
const EXPLAINED = new Set(["COMPLETED", "NEEDS_HUMAN_REVIEW", "INSUFFICIENT_EVIDENCE"]);
// KHÔNG có "Chuyển lên cấp rà soát 2": hệ thống chỉ có ba vai và ô rà soát này
// đã chỉ quản lý dùng được, nên nó là chuyển lên một cấp không tồn tại. Bốn lựa
// chọn còn lại đều đẩy vụ việc đi một hướng thật (xem _DECISION_STATES).
const REVIEW_ACTIONS = [
  ["CONTINUE_MONITORING", "Tiếp tục giám sát"],
  ["REQUEST_MORE_INFORMATION", "Yêu cầu thêm thông tin"],
  ["REVIEW_FOR_SAR_STR", "Rà soát để lập báo cáo SAR/STR"],
  ["CLOSE_AS_LIKELY_FALSE_POSITIVE", "Đóng — nhiều khả năng là cảnh báo giả"],
] as const;

export function InvestigationPanel({ alertId }: { alertId: string }) {
  const { pushToast, currentUser } = useApp();
  // Người ĐIỀU TRA là người kết luận, và đó là Chuyên viên.
  //
  // Ô này từng khoá theo REVIEW_INVESTIGATION (quyền của Quản lý) — chuyên viên
  // điều tra xong không ghi được kết luận của chính mình. Sửa sang
  // INVESTIGATE_CASE thì chuyên viên ghi được, nhưng Quản lý cũng ghi được, tức
  // vừa kết luận vừa phê duyệt. PREPARE_SAR nay CHỈ Chuyên viên có, và nó đúng
  // là quyền "người lập hồ sơ" — cùng một vai với người kết luận.
  const canReview = currentUser?.permissions?.includes(PERMISSIONS.PREPARE_SAR) ?? false;
  const [starting, setStarting] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  // Mặc định chỉ hiện ~6 bằng chứng chính; phần còn lại mở theo yêu cầu để view
  // không bị hàng chục evidence ID đẩy phần kết luận xuống dưới.
  const [showAllEvidence, setShowAllEvidence] = useState(false);
  const EVIDENCE_PREVIEW = 6;
  const [decision, setDecision] = useState<(typeof REVIEW_ACTIONS)[number][0]>("REVIEW_FOR_SAR_STR");
  const [reason, setReason] = useState("");
  const latest = useApi(() => api.latestInvestigation(alertId), [alertId]);
  const investigationId = latest.data?.investigation_id ?? null;
  const evidence = useApi(
    () => (investigationId ? api.investigationEvidence(investigationId) : Promise.resolve([])),
    [investigationId, latest.data?.updated_at],
  );
  // Tra loại bằng chứng theo id để nút dẫn chiếu hiện nhãn dễ đọc thay mã EV thô.
  const evidenceById = useMemo(
    () => new Map((evidence.data ?? []).map((e) => [e.evidence_id, e])),
    [evidence.data],
  );
  // Bấm một dẫn chiếu bằng chứng: mở hết danh sách, rồi bung + cuộn tới đúng mục.
  const openEvidence = useCallback((evidenceId: string) => {
    setShowAllEvidence(true);
    window.setTimeout(() => {
      const el = document.getElementById(`ev-${evidenceId}`);
      if (el instanceof HTMLDetailsElement) el.open = true;
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
  }, []);
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

  // Hẹn giờ bám vào *trạng thái*, không bám vào cả đối tượng dữ liệu. Mỗi lượt
  // hỏi thành công trả về một đối tượng mới, nên nếu để `latest.data` trong deps
  // thì cứ hai giây React lại huỷ và tạo lại bộ đếm — nhịp hỏi trôi đi và có lúc
  // dồn cục. Trạng thái chỉ đổi vài lần trong cả phiên, nên bộ đếm dựng đúng một
  // lần cho mỗi giai đoạn.
  const status = latest.data?.status;
  const running = status !== undefined && ACTIVE.has(status);
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(latest.reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, latest.reload]);

  async function start() {
    setStarting(true);
    try {
      await api.investigateAlert(alertId);
      pushToast({ tone: "success", title: "Đã bắt đầu điều tra" });
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

  // Chỉ vẽ khung chờ khi thật sự chưa có gì. Trong lúc tác tử chạy, mỗi hai giây
  // lại có một lượt hỏi mới; thay cả bảng bằng khung chờ ở mỗi lượt là nguyên
  // nhân khiến màn hình giật suốt cả phút.
  if (latest.loading) return <LoadingSkeleton rows={5} />;
  if (latest.error) return <ErrorState detail={latest.error} onRetry={latest.reload} />;
  if (!latest.data) {
    return (
      <Panel title="Điều tra bằng AI">
        <EmptyState
          title="Chưa có phiên điều tra"
          detail="Khởi động phân tích tự động. Quy trình chạy nền và không tự thực hiện quyết định nghiệp vụ."
        />
        <button
          type="button"
          disabled={starting}
          onClick={start}
          className="mx-auto mt-3 flex items-center gap-1.5 rounded-control bg-primary px-4 py-2 text-2xs font-semibold text-app disabled:opacity-50"
        >
          <Play size={13} /> {starting ? "Đang bắt đầu…" : "Bắt đầu điều tra"}
        </button>
      </Panel>
    );
  }

  const inv = latest.data;
  const risk = inv.risk_summary;
  // Nhánh nào THẬT SỰ chấm ra cảnh báo này. Bảng phân rã cũ bắt chuyên viên tự
  // dò trong năm dòng để tìm dòng duy nhất có dữ liệu; ở đây rút thẳng ra tên.
  const detectedBy = Object.entries(risk?.components ?? {})
    .filter(([, c]) => c.available)
    .map(([name]) => riskComponentLabel(name))
    .join(" và ");
  return (
    <div className="space-y-3">
      <Panel
        title="Trạng thái điều tra"
        action={
          <button
            type="button"
            onClick={latest.reload}
            className="text-ink-mid hover:text-ink-hi"
            aria-label={latest.refreshing ? "Đang cập nhật" : "Làm mới"}
          >
            {/* Biểu tượng quay là dấu hiệu duy nhất cho biết màn hình còn sống
                trong lúc chờ. Trước đây không có gì cả, nên một phiên dài trông
                y hệt một phiên đã treo. */}
            <RefreshCw size={13} className={latest.refreshing ? "animate-spin" : undefined} />
          </button>
        }
      >
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            tone={inv.status === "COMPLETED" ? "ok" : inv.status === "FAILED" ? "risk" : "primary"}
            label={investigationStatusLabel(inv.status)}
          />
          <span className="text-2xs text-ink-low">
            Cập nhật lúc {formatDateTime(inv.snapshot_time)}
          </span>
        </div>
        {running && (
          // Nói rõ mất bao lâu. Không có câu này, người dùng nhìn "0 lần gọi
          // công cụ" đứng yên vài chục giây và tưởng hệ thống hỏng.
          <p className="mt-2 flex items-center gap-1.5 text-2xs text-ink-mid">
            <Loader2 size={12} className="animate-spin" />
            Đang phân tích trong nền, thường mất 40–90 giây. Màn hình tự cập nhật, không cần tải lại
            trang.
          </p>
        )}
        {inv.failure_reason && <p className="mt-2 text-2xs text-risk">{investigationTextVi(inv.failure_reason)}</p>}
        <p className="mt-2 text-2xs text-ink-low">
          Nhật ký chỉ ghi các bước xử lý và bằng chứng liên quan.
        </p>
      </Panel>

      {/* Chỉ còn ĐIỂM và NGUỒN phát hiện.
          Bảng phân rã theo nhánh đã bỏ: nó liệt kê năm nhánh mà bốn trong số đó
          luôn ghi "không có dữ liệu — không phải điểm 0", còn nhánh thật thì hiện
          "điểm 1.000 · trọng số 1.00 · mức đóng góp 1.000". Ba con số ấy là thang
          0-1 của bộ chấm, không phải thang 100 mà cả console dùng — "1.000" đọc
          trong tiếng Việt còn thành "một nghìn". Chuyên viên không quyết định gì
          khác đi nhờ chúng; điều họ cần là điểm bao nhiêu và ai chấm. Phân rã
          theo nhánh vẫn còn nguyên ở trang Giám sát mô hình (chỉ Admin). */}
      {risk.components && (
        <Panel title="Điểm rủi ro">
          <div className="flex items-baseline gap-2">
            <span className="tabular text-2xl font-bold text-ink-hi">
              {Math.round((risk.final_risk_score ?? 0) * 100)}
            </span>
            <span className="text-2xs text-ink-mid">trên thang một trăm</span>
          </div>
          {detectedBy && (
            <p className="mt-1 text-2xs text-ink-mid">
              Do <span className="text-ink-hi">{detectedBy}</span> phát hiện.
            </p>
          )}
          <p className="mt-3 border-t border-line pt-2 text-2xs text-ink-low">
            Điểm dùng để xếp thứ tự ưu tiên rà soát, không phải kết luận về hành vi rửa tiền.
          </p>
        </Panel>
      )}

      {explanation.data && (
        <Panel title="Vì sao cảnh báo này được tạo?">
          {inv.status !== "COMPLETED" && (
            /* Câu cũ chỉ ghi "chưa vượt qua bước phản biện", và cách đọc tự
               nhiên nhất là "hệ thống không tin chính nó" — khiến chuyên viên
               nghi ngờ cả điểm rủi ro. Đo trên 227 phiên: bộ phản biện chưa
               một lần nào nêu INVALID_SCORE. Nó chỉ soi phần chữ do tác tử
               viết. Nên tách bạch hai thứ ngay tại đây. */
            <div className="mb-3 rounded-control border border-warn/30 bg-warn/10 p-2.5 text-2xs">
              <p className="font-semibold text-warn-soft">Phần diễn giải tự động chưa dùng được để lập báo cáo</p>
              <p className="mt-1 text-ink-mid">
                <b className="text-ink-hi">Điểm rủi ro vẫn có hiệu lực.</b> Nó do bộ phát hiện chấm và đã được chốt; bộ
                phản biện không chấm lại điểm, chỉ kiểm xem từng câu bên dưới có dẫn đủ bằng chứng hay không.
              </p>
              <p className="mt-1 text-ink-mid">
                Những câu chưa dẫn được nguồn nằm ở mục Kiểm tra bằng chứng. Hãy tự đối chiếu với phần Bằng
                chứng trước khi dùng.
              </p>
            </div>
          )}
          <p className="text-body leading-relaxed text-ink-hi">{investigationTextVi(explanation.data.summary)}</p>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <ExplanationList
              title="DỮ KIỆN"
              items={explanation.data.claims.filter((claim) => claim.claim_type === "FACT")}
              evidenceById={evidenceById}
              onOpen={openEvidence}
            />
            <ExplanationList
              title="SUY LUẬN"
              items={explanation.data.claims.filter((claim) => claim.claim_type === "INFERENCE")}
              evidenceById={evidenceById}
              onOpen={openEvidence}
            />
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
              {(showAllEvidence ? (evidence.data ?? []) : (evidence.data ?? []).slice(0, EVIDENCE_PREVIEW)).map((item) => (
                <details key={item.evidence_id} id={`ev-${item.evidence_id}`} className="scroll-mt-4 rounded-control border border-line bg-elev p-2.5">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-2xs text-ink-hi">
                    <ChevronRight size={12} />
                    {/* Mã EV-<băm 24 ký tự> từng in ở đây. Nó không tra cứu được
                        thứ gì cho chuyên viên, và nút trích dẫn phía trên đã trỏ
                        thẳng tới bằng chứng bằng nhãn tiếng Việt. */}
                    <span className="font-semibold">{evidenceTypeLabel(item.type)}</span>
                  </summary>
                  <div className="mt-2 border-t border-line pt-2 text-2xs text-ink-mid">
                    <EvidenceBody type={item.type} payload={item.payload} />
                  </div>
                </details>
              ))}
              {(evidence.data?.length ?? 0) > EVIDENCE_PREVIEW && (
                <button
                  type="button"
                  onClick={() => setShowAllEvidence((v) => !v)}
                  className="w-full rounded-control border border-line py-1.5 text-2xs font-medium text-ink-mid hover:border-line-emphasis hover:text-ink-hi"
                >
                  {showAllEvidence
                    ? "Thu gọn"
                    : `Xem tất cả ${evidence.data?.length} bằng chứng`}
                </button>
              )}
            </div>
          )}
        </Panel>

        <Panel title="Nhật ký xử lý">
          {/* Mặc định thu gọn: chuỗi điều phối/gọi công cụ/phản biện là chi tiết
              kỹ thuật để kiểm toán, không phải thứ chuyên viên đọc ở lượt đầu. */}
          <details>
            <summary className="flex cursor-pointer list-none items-center gap-1.5 text-2xs font-medium text-ink-mid hover:text-ink-hi">
              <ChevronRight size={12} />
              Xem {(trace.data ?? []).length} bước xử lý chi tiết
            </summary>
            <ol className="mt-3 space-y-3">
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
                    
                  </div>
                </div>
              </li>
            ))}
            </ol>
          </details>
        </Panel>
      </div>

      {inv.validation && (
        <Panel title="Kiểm tra bằng chứng">
          <div className="flex flex-wrap items-center gap-2">
            {inv.validation.status === "PASS" ? <CheckCircle2 className="text-ok" size={18} /> : <ShieldAlert className="text-risk" size={18} />}
            <span className="font-semibold text-ink-hi">{validationStatusLabel(inv.validation.status)}</span>
            {/* "confidence" của bộ phản biện là mức TỰ ĐÁNH GIÁ về phần chữ nó
                kiểm, KHÔNG phải xác suất rửa tiền hay độ chính xác khách quan.
                Ghi rõ để chuyên viên không đọc 0,98 thành "98% đúng". */}
            <span
              className="tabular text-2xs text-ink-mid"
              title="Mức tự đánh giá của bộ phản biện về phần diễn giải bằng chữ — không phải xác suất rửa tiền hay độ chính xác khách quan."
            >
              tự đánh giá {inv.validation.confidence.toFixed(2)}
            </span>
          </div>
          <p className="mt-1.5 text-micro text-ink-low">
            Điều cần đối chiếu là mỗi câu đã dẫn được bằng chứng hay chưa (mục Bằng chứng), không phải con số tự đánh giá này.
          </p>
          {inv.validation.issues.map((issue, index) => (
            <div key={`${issue.type}-${index}`} className="mt-2 rounded-control border border-risk/30 bg-risk-soft p-2 text-2xs text-ink-hi">
              <strong>{validationIssueLabel(issue.type)}</strong> — {investigationTextVi(issue.detail)}
            </div>
          ))}
        </Panel>
      )}

      {/* Phiên dừng giữa chừng thì phải có đường chạy lại NGAY TẠI ĐÂY.
          Nút "Bắt đầu điều tra" chỉ hiện khi cảnh báo chưa từng có phiên nào,
          nên sau một phiên trượt nó biến mất và chuyên viên không còn cách nào
          cho chạy lại từ giao diện — dù API vẫn tạo phiên mới bình thường.
          `investigateAlert` chỉ tái dùng phiên đang QUEUED/INVESTIGATING; gặp
          phiên đã kết thúc nó mở phiên mới, nên dùng lại đúng hàm `start`. */}
      {["INSUFFICIENT_EVIDENCE", "NEEDS_HUMAN_REVIEW", "FAILED"].includes(inv.status) && (
        <Panel title="Phiên điều tra dừng giữa chừng">
          <div className="space-y-3 text-2xs">
            <p className="text-ink-mid">
              {inv.failure_reason ??
                "Phiên dừng trước khi mọi nhận định được đối chiếu xong với bằng chứng."}
            </p>
            <p className="text-ink-mid">
              Bản nháp bên dưới <span className="text-ink-hi">chưa được đóng dấu kiểm chứng</span>. Đọc theo
              từng nhận định và đối chiếu với mục Bằng chứng trước khi dùng bất kỳ con số nào.
            </p>
            {/* Dừng vì GIẬM CHÂN thì chạy lại cho ra đúng kết quả cũ — quy
                trình đã tự đo được điều đó và dừng sớm. Mời bấm lại ở đây là
                lời khuyên sai, nên nút bị hạ xuống thứ yếu kèm cảnh báo thẳng. */}
            {/KHÔNG tiến triển/.test(inv.failure_reason ?? "") ? (
              <>
                <p className="rounded-control border border-warn/30 bg-warn-soft p-3 text-ink-hi">
                  Quy trình đã thử lại và nhận đúng những vấn đề cũ, nên nó dừng sớm thay vì chạy tiếp.
                  Chạy lại nhiều khả năng cho cùng kết quả — việc cần làm là đọc mục Bằng chứng rồi
                  ghi quyết định ở ô bên dưới.
                </p>
                <button
                  type="button"
                  disabled={starting}
                  onClick={start}
                  className="flex items-center gap-1.5 rounded-control border border-line px-4 py-2 text-2xs font-semibold text-ink-mid disabled:opacity-50"
                >
                  <Play size={13} /> {starting ? "Đang chạy lại…" : "Vẫn chạy lại"}
                </button>
              </>
            ) : (
              <button
                type="button"
                disabled={starting}
                onClick={start}
                className="flex items-center gap-1.5 rounded-control bg-primary px-4 py-2 text-2xs font-semibold text-app disabled:opacity-50"
              >
                <Play size={13} /> {starting ? "Đang chạy lại…" : "Chạy lại điều tra"}
              </button>
            )}
            <p className="text-ink-mid">
              Chạy lại mở một phiên mới và giữ nguyên phiên cũ trong nhật ký, không ghi đè.
            </p>
          </div>
        </Panel>
      )}

      {/* Ô kết luận của NGƯỜI ĐIỀU TRA. "Đóng — cảnh báo giả" rẽ theo mức rủi
          ro: dưới ngưỡng thì đóng thẳng, từ ngưỡng trở lên thì thành một đề nghị
          nằm chờ Quản lý chốt ở trang Phê duyệt SAR. */}
      {canReview && ["COMPLETED", "INSUFFICIENT_EVIDENCE", "NEEDS_HUMAN_REVIEW"].includes(inv.status) && (
        <Panel title="Kết luận điều tra">
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

function ExplanationList({
  title,
  items,
  evidenceById,
  onOpen,
}: {
  title: string;
  items: Array<{ claim_id: string; claim: string; evidence_refs: string[] }>;
  evidenceById: Map<string, { evidence_id: string; type: string }>;
  onOpen: (evidenceId: string) => void;
}) {
  return (
    <div>
      <h4 className="mb-2 text-2xs font-semibold uppercase tracking-wider text-ink-mid">{title}</h4>
      {items.length === 0 ? (
        <p className="text-2xs text-ink-low">Không có.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.claim_id} className="text-body text-ink-hi">
              {investigationTextVi(item.claim)}
              {item.evidence_refs.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {item.evidence_refs.map((ref) => {
                    const ev = evidenceById.get(ref);
                    // Chỉ tạo nút BẤM ĐƯỢC khi bằng chứng có thật ở panel dưới;
                    // nếu không, không hiện gì (không để mã EV chết như link giả).
                    if (!ev) return null;
                    return (
                      <button
                        key={ref}
                        type="button"
                        onClick={() => onOpen(ref)}
                        title="Mở bằng chứng liên quan ở mục Bằng chứng"
                        className="inline-flex items-center gap-1 rounded-control border border-info/30 bg-info/[0.08] px-1.5 py-0.5 text-3xs font-medium text-info-soft transition-colors hover:border-info/60 hover:text-info"
                      >
                        <ScanSearch size={10} aria-hidden />
                        {evidenceTypeLabel(ev.type)}
                      </button>
                    );
                  })}
                </div>
              )}
            </li>
          ))}
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
