import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { conf, duration, int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { ErrorState, PageShell } from "../components/ui";
import { Chip, Empty, KpiCard, Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * AI Agent Runs — danh sách và console chi tiết một lần chạy.
 *
 * Màn hình này tồn tại để trả lời một câu hỏi: agent đã làm gì, dựa vào bằng
 * chứng nào, và ở đâu nó bị chặn. Mỗi bước ghi rõ công cụ, đầu vào, đầu ra và
 * danh sách bằng chứng viện dẫn — một kết luận không có `evidence_refs` là
 * kết luận không kiểm chứng được.
 */

/**
 * Ba tác tử chạy nối tiếp trong một phiên điều tra, theo đúng thứ tự này.
 * Backend trả về `agent_name` — tên thật trong `investigation_agent_run` —
 * nên nhãn ở đây phải khớp với ba giá trị đó, không phải ba cấp tổ chức.
 */
const TIER_LABEL: Record<string, string> = {
  investigation_supervisor: "1 · Điều phối điều tra",
  explanation_agent: "2 · Giải thích rủi ro",
  evidence_critic: "3 · Phản biện bằng chứng",
};

const STATUS_COLOR: Record<string, string> = {
  running: C.info,
  succeeded: C.ok,
  failed: C.risk,
  timeout: C.warn,
};

const STATUS_LABEL: Record<string, string> = {
  running: "Đang chạy",
  succeeded: "Hoàn tất",
  failed: "Thất bại",
  timeout: "Quá hạn",
};

/**
 * `partial` là trạng thái đáng chú ý nhất: công cụ chạy xong nhưng chỉ lấy được
 * một phần dữ liệu — thường vì bằng chứng đồ thị chưa phủ hết tài khoản. Tô màu
 * cảnh báo chứ không tô xanh, vì kết luận dựng trên nó yếu hơn.
 */
const STEP_COLOR: Record<string, string> = {
  succeeded: C.ok,
  failed: C.risk,
  timeout: C.risk,
  partial: C.warn,
};

const STEP_LABEL: Record<string, string> = {
  succeeded: "Hoàn tất",
  failed: "Lỗi",
  timeout: "Quá hạn",
  partial: "Thiếu một phần",
};

/** Bảy công cụ mà tác tử được phép gọi — khớp ràng buộc CHECK của bảng. */
const TOOL_LABEL: Record<string, string> = {
  GetRiskBreakdown: "Bóc tách điểm rủi ro",
  GetAccountBehavior: "Hành vi tài khoản",
  GetTransactions: "Truy vấn giao dịch",
  GetGraphEvidence: "Bằng chứng đồ thị",
  GetGraphNeighborhood: "Lân cận trên đồ thị",
  GetTypology: "Nhóm hành vi rửa tiền",
  GetAnomalyExplanation: "Giải thích bất thường",
};

function summaryVi(value: string): string {
  return value
    .replace(/^alert_id=/, "mã cảnh báo=")
    .replace(/^seed=/, "đỉnh gốc=")
    .replace(/, depth=/, ", độ sâu=")
    .replace(/^accounts=/, "số tài khoản=")
    .replace(/^entities=/, "số thực thể=")
    .replace(/^addresses=/, "số địa chỉ=")
    .replace(/^vasp=/, "VASP=")
    .replace(/^case=/, "vụ việc=")
    .replace(/^priority=/, "mức ưu tiên=")
    .replace(/\bhop\b/g, "chặng")
    .replace(/\btypology\b/gi, "nhóm hành vi");
}

const LIST_COLS = "170px 200px 130px 150px 90px 100px 90px";

export function AgentsPage() {
  const navigate = useNavigate();
  const runs = useApi(() => api.agentRuns(), [], "agent-runs");
  // `rows` chỉ là danh sách gần nhất (giới hạn để hiển thị bảng). Các con số
  // TỔNG lấy từ aggregate toàn bảng do API trả về — KHÔNG đếm rows.length, nếu
  // không thẻ "Tổng lần chạy" sẽ kẹt ở đúng giới hạn (trước đây luôn = 200).
  const rows = runs.data?.rows ?? [];
  const totalRuns = runs.data?.total ?? 0;
  const criticRuns = runs.data?.critic_count ?? 0;
  const failedTotal = runs.data?.failed_count ?? 0;
  const totalTokens = runs.data?.total_tokens ?? 0;

  return (
    <PageShell variant="dense">
      <ScreenTitle title="Các lượt chạy tác tử AI" meta="Mọi kết luận của tác tử đều phải qua người có thẩm quyền" />

      {/* Đặt kỳ vọng đúng: đây là view KỸ THUẬT/kiểm toán của đường ống tác tử,
          không phải màn làm việc của chuyên viên. Phần diễn giải hướng nghiệp vụ
          nằm ở tab "Điều tra bằng AI" trong từng cảnh báo/vụ việc. */}
      <p className="text-xs leading-relaxed text-ink-low">
        View kỹ thuật để kiểm toán/gỡ lỗi đường ống tác tử. Chuyên viên đọc kết luận hướng nghiệp vụ ở tab
        “Điều tra bằng AI” của từng cảnh báo/vụ việc, không cần theo dõi từng lượt chạy ở đây.
      </p>

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard label="Tổng lần chạy" value={totalRuns} delta="trong hệ thống" />
        <KpiCard label="Lượt phản biện" value={criticRuns} valueColor={C.warn} delta="mỗi phiên đều bị soát lại" />
        <KpiCard label="Thất bại" value={failedTotal} valueColor={C.risk} delta="cần xem lại" />
        <KpiCard
          label="Token đã dùng"
          value={int(totalTokens)}
          valueColor={C.agent}
          delta="chi phí suy luận (kỹ thuật)"
        />
      </div>

      <Panel bodyClassName="overflow-x-auto px-0">
        <div className="min-w-[900px]">
          <div
            className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
            style={{ gridTemplateColumns: LIST_COLS }}
          >
            <span>Mã lượt chạy</span>
            <span>Tác tử</span>
            <span>Vụ việc</span>
            <span>Bắt đầu</span>
            <span>Số bước</span>
            <span title="Mức tự đánh giá của tác tử về phần diễn giải — không phải xác suất khách quan hay độ chính xác.">
              Tự đánh giá
            </span>
            <span>Trạng thái</span>
          </div>
          {runs.loading && <Skeleton rows={4} />}
          {runs.error && <ErrorState detail={runs.error} onRetry={runs.reload} />}
          {!runs.loading && !runs.error && !rows.length && (
            <Empty
              text="Chưa có lượt điều tra tác tử nào"
              hint="Tác tử chỉ chạy sau khi chuyên viên mở quy trình điều tra; release mô hình không tự tạo kết luận."
            />
          )}
          {rows.map((r) => (
            <div
              key={r.id}
              role="button"
              tabIndex={0}
              onClick={() => navigate(`/agents/${r.id}`)}
              onKeyDown={(e) => e.key === "Enter" && navigate(`/agents/${r.id}`)}
              className="grid cursor-pointer items-center gap-2 border-b border-line-faint px-3 py-2 text-base transition-colors hover:bg-elev"
              style={{ gridTemplateColumns: LIST_COLS }}
            >
              {/* Mã hash dài rút gọn để bảng quét dọc được; full id ở tooltip. */}
              <span className="font-mono text-xs text-primary" title={r.id}>
                {r.id.length > 14 ? `${r.id.slice(0, 14)}…` : r.id}
              </span>
              <span className="truncate-1 text-xs text-ink-soft">{TIER_LABEL[r.tier] ?? r.tier}</span>
              <span className="font-mono text-xs">{r.case_id ?? "—"}</span>
              <span className="text-xs text-ink-soft">{formatDateTime(r.started_at)}</span>
              <span className="tabular font-mono text-xs">{r.step_count}</span>
              <span
                className="tabular font-mono text-xs"
                title="Mức tự đánh giá của tác tử — không phải xác suất khách quan."
              >
                {conf(r.confidence)}
              </span>
              <Chip color={STATUS_COLOR[r.status] ?? C.inkSoft}>{STATUS_LABEL[r.status] ?? r.status}</Chip>
            </div>
          ))}
        </div>
      </Panel>
    </PageShell>
  );
}

export function AgentRunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const run = useApi(() => api.agentRun(runId), [runId]);
  const r = run.data;

  return (
    <PageShell variant="dense">
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => navigate("/agents")} className="text-base text-ink-soft hover:text-ink-hi">
          ← Các lượt chạy tác tử
        </button>
        <span className="font-mono text-base text-primary">{runId}</span>
        {r && <Chip color={STATUS_COLOR[r.status] ?? C.inkSoft}>{STATUS_LABEL[r.status] ?? r.status}</Chip>}
        {r && <span className="text-2xs text-ink-low">{TIER_LABEL[r.tier] ?? r.tier}</span>}
      </div>

      {run.loading && <Skeleton rows={8} />}
      {run.error && <div className="rounded-panel border border-risk/40 bg-risk/10 px-3.5 py-2.5 text-sm text-risk-soft">{run.error}</div>}

      {r && (
        <>
          <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))" }}>
            <KpiCard label="Phiên bản mô hình" value={<span className="text-2xl">{r.model_version}</span>} />
            <KpiCard label="Tự đánh giá" value={conf(r.confidence)} valueColor={C.agent} delta="tác tử tự khai báo, không phải xác suất khách quan" />
            <KpiCard label="Số bước" value={r.step_count} />
            <KpiCard label="Token đã dùng" value={int(r.token_cost)} valueColor={C.agent} delta="chi phí suy luận (kỹ thuật)" />
            <KpiCard
              label="Thời lượng"
              value={
                r.finished_at
                  ? duration(new Date(r.finished_at).getTime() - new Date(r.started_at).getTime())
                  : "đang chạy"
              }
            />
          </div>

          <Panel title="Kết luận của tác tử" subtitle="Chưa có hiệu lực cho tới khi người có thẩm quyền duyệt">
            <p className="text-base leading-relaxed text-ink-mid">{summaryVi(r.conclusion) || "—"}</p>
            {r.tier === "evidence_critic" && (
              <div className="mt-3 rounded-control border border-warn/35 bg-warn/10 px-3 py-2 text-xs leading-relaxed text-warn-soft">
                Đây là tác tử phản biện: nó soát lại lời giải thích và chỉ ra chỗ thiếu căn cứ. Kết quả của nó không kết
                luận vụ việc — tác tử đề xuất, con người quyết định. Không có đường nào để tác tử tự đóng hồ sơ.
              </div>
            )}
          </Panel>

          <Panel title="Nhật ký thực thi" subtitle="Từng lần gọi công cụ, kèm bằng chứng viện dẫn">
            <ol className="flex flex-col">
              {r.steps.map((s, i) => (
                <li key={s.id} className="relative flex gap-3 pb-4 last:pb-0">
                  {/* Đường nối dọc giữa các bước; bước cuối không cần đuôi. */}
                  {i < r.steps.length - 1 && (
                    <span className="absolute bottom-0 left-[7px] top-5 w-px bg-line" aria-hidden />
                  )}
                  <span
                    className="mt-1.5 h-[15px] w-[15px] flex-none rounded-full border-2"
                    style={{ borderColor: STEP_COLOR[s.status] ?? C.inkLow, background: C.app }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-base text-ink-hi">{TOOL_LABEL[s.tool] ?? s.tool}</span>
                      <Chip color={STEP_COLOR[s.status] ?? C.inkSoft}>{STEP_LABEL[s.status] ?? s.status}</Chip>
                      <span className="tabular font-mono text-2xs text-ink-low">{duration(s.duration_ms)}</span>
                    </div>
                    <div className="mt-1 font-mono text-2xs text-ink-low">→ {summaryVi(s.input_summary)}</div>
                    <div className="mt-0.5 text-xs leading-relaxed text-ink-mid">{summaryVi(s.output_summary)}</div>
                    {s.evidence_refs.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {s.evidence_refs.map((ref) => (
                          <span
                            key={ref}
                            className="rounded-[6px] border border-primary/30 px-2 py-px font-mono text-2xs text-primary"
                          >
                            {ref}
                          </span>
                        ))}
                      </div>
                    )}
                    {s.status === "partial" && (
                      <div className="mt-1.5 text-2xs leading-relaxed text-warn-soft">
                        Công cụ chỉ lấy được một phần dữ liệu — thường vì bằng chứng đồ thị chưa phủ hết tài khoản
                        trong phạm vi hỏi. Ghi lại nguyên trạng thay vì lấp chỗ trống: một kết luận dựng trên bằng
                        chứng thiếu phải được nhìn thấy là thiếu.
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </>
      )}
    </PageShell>
  );
}
