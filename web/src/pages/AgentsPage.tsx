import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { conf, duration, int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
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

const TIER_LABEL: Record<string, string> = {
  A_INSTITUTION: "Tầng A · Tổ chức tài chính",
  B_REGULATOR: "Tầng B · Cơ quan quản lý",
  C_INVESTIGATION: "Tầng C · Điều tra",
};

const STATUS_COLOR: Record<string, string> = {
  running: C.info,
  succeeded: C.ok,
  failed: C.risk,
  needs_human: C.warn,
};

const STATUS_LABEL: Record<string, string> = {
  running: "Đang chạy",
  succeeded: "Hoàn tất",
  failed: "Thất bại",
  needs_human: "Chờ người duyệt",
};

const STEP_COLOR: Record<string, string> = {
  ok: C.ok,
  error: C.risk,
  skipped: C.inkLow,
  blocked: C.warn,
};

const STEP_LABEL: Record<string, string> = {
  ok: "Hoàn tất",
  error: "Lỗi",
  skipped: "Đã bỏ qua",
  blocked: "Bị chặn",
};

const TOOL_LABEL: Record<string, string> = {
  query_transactions: "Truy vấn giao dịch",
  retrieve_evidence: "Truy hồi bằng chứng",
  screen_watchlists: "Đối chiếu danh sách theo dõi",
  analyze_network: "Phân tích mạng lưới",
  calculate_risk: "Tính điểm rủi ro",
  draft_case_summary: "Soạn tóm tắt vụ việc",
  fetch_alert_context: "Lấy bối cảnh cảnh báo",
  expand_entity_graph: "Mở rộng đồ thị thực thể",
  device_correlation: "Đối chiếu thiết bị",
  screen_watchlist: "Đối chiếu danh sách theo dõi",
  trace_crypto_exposure: "Truy vết phơi nhiễm tài sản mã hoá",
  request_vasp_records: "Yêu cầu hồ sơ từ VASP",
  draft_str_narrative: "Soạn nội dung báo cáo STR",
  request_human_review: "Yêu cầu chuyên viên rà soát",
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
  const runs = useApi(() => api.agentRuns(), []);
  const rows = runs.data ?? [];

  const needsHuman = rows.filter((r) => r.status === "needs_human").length;
  const blockedTotal = rows.reduce((s, r) => s + (r.status === "failed" ? 1 : 0), 0);

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
      <ScreenTitle title="Các lượt chạy tác tử AI" meta="Mọi kết luận của tác tử đều phải qua người có thẩm quyền" />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard label="Tổng lần chạy" value={rows.length} delta="trong hệ thống" />
        <KpiCard label="Chờ người duyệt" value={needsHuman} valueColor={C.warn} delta="con người tham gia quyết định" />
        <KpiCard label="Thất bại" value={blockedTotal} valueColor={C.risk} delta="cần xem lại" />
        <KpiCard
          label="Tổng đơn vị từ"
          value={int(rows.reduce((s, r) => s + r.token_cost, 0))}
          valueColor={C.agent}
          delta="chi phí suy luận"
        />
      </div>

      <Panel bodyClassName="overflow-x-auto px-0">
        <div className="min-w-[900px]">
          <div
            className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
            style={{ gridTemplateColumns: LIST_COLS }}
          >
            <span>Mã lượt chạy</span>
            <span>Tầng năng lực</span>
            <span>Vụ việc</span>
            <span>Bắt đầu</span>
            <span>Số bước</span>
            <span>Độ tin cậy</span>
            <span>Trạng thái</span>
          </div>
          {runs.loading && <Skeleton rows={4} />}
          {!runs.loading && !rows.length && (
            <Empty text="Chưa có lượt chạy tác tử nào" hint="Chạy scripts/abm_generate.py để sinh dữ liệu" />
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
              <span className="font-mono text-xs text-primary">{r.id}</span>
              <span className="truncate-1 text-xs text-ink-soft">{TIER_LABEL[r.tier] ?? r.tier}</span>
              <span className="font-mono text-xs">{r.case_id ?? "—"}</span>
              <span className="text-xs text-ink-soft">{formatDateTime(r.started_at)}</span>
              <span className="tabular font-mono text-xs">{r.step_count}</span>
              <span className="tabular font-mono text-xs">{conf(r.confidence)}</span>
              <Chip color={STATUS_COLOR[r.status] ?? C.inkSoft}>{STATUS_LABEL[r.status] ?? r.status}</Chip>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

export function AgentRunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const run = useApi(() => api.agentRun(runId), [runId]);
  const r = run.data;

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
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
            <KpiCard label="Độ tin cậy" value={conf(r.confidence)} valueColor={C.agent} delta="tác tử tự khai báo" />
            <KpiCard label="Số bước" value={r.step_count} />
            <KpiCard label="Đơn vị từ" value={int(r.token_cost)} valueColor={C.agent} />
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
            {r.status === "needs_human" && (
              <div className="mt-3 rounded-control border border-warn/35 bg-warn/10 px-3 py-2 text-xs leading-relaxed text-warn-soft">
                Tác tử dừng lại và chuyển cho người duyệt. Đây là hành vi đúng thiết kế: tác tử đề xuất, con người quyết
                định. Không có đường nào để tác tử tự kết luận một vụ việc.
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
                    {s.status === "blocked" && (
                      <div className="mt-1.5 text-2xs leading-relaxed text-warn-soft">
                        Bước này bị chặn vì vai trò hiện tại không có thẩm quyền. Ranh giới quyền truy cập được cưỡng
                        chế ở tầng công cụ, không phụ thuộc vào việc mô hình có "biết điều" hay không.
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
        </>
      )}
    </div>
  );
}
