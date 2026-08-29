import {
  ChartNoAxesCombined,
  ExternalLink,
  RefreshCw,
  ScrollText,
  Waypoints,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../../api/client";
import type { FcAgentRun } from "../../api/client";
import { conf, duration, int } from "../../api/fcFormat";
import { agentLabel, formatDateTime } from "../../api/format";
import { useApi } from "../../api/useApi";
import { Empty, Skeleton } from "../fc/primitives";
import { C } from "../../design/palette";

/**
 * Giám sát vận hành — BA giao diện tách bạch, không dồn hết vào Grafana:
 *   • Chỉ số  → nhúng bảng Grafana (Prometheus). Grafana CHỈ để trực quan hoá metrics.
 *   • Nhật ký → giao diện gốc, đọc thẳng lượt chạy tác tử (task) + từng bước gọi công cụ.
 *   • Traces  → giao diện gốc, dựng waterfall span của một lượt chạy.
 * Logs/Traces đọc dữ liệu có cấu trúc trong DB (investigation_agent_run /
 * investigation_tool_call) nên luôn chạy, không phụ thuộc stack Loki/Jaeger.
 */

const GRAFANA_ARGS = "orgId=1&from=now-6h&to=now&refresh=30s&theme=dark&kiosk=tv";

/**
 * Hai bảng, hai câu hỏi.
 *
 * Trước đây chỉ có bảng tác tử, nên tab Chỉ số trả lời được "gọi Gemini tốn bao
 * nhiêu" mà không trả lời được "hệ thống phản hồi nhanh hay chậm" — dù độ trễ
 * HTTP vẫn được đo và vẫn có cảnh báo dựa trên nó. Bảng Hệ thống đứng trước vì
 * đó là câu hỏi người trực hỏi đầu tiên.
 */
const GRAFANA_BOARDS = [
  { id: "system", label: "Hệ thống", uid: "fin07-system", slug: "fin-07-he-thong" },
  { id: "agent", label: "Tác tử AI", uid: "fin07-observability", slug: "fin-07-observability" },
] as const;

type BoardId = (typeof GRAFANA_BOARDS)[number]["id"];

function boardUrl(id: BoardId): string {
  const board = GRAFANA_BOARDS.find((b) => b.id === id) ?? GRAFANA_BOARDS[0];
  return `/grafana/d/${board.uid}/${board.slug}?${GRAFANA_ARGS}`;
}

type Tab = "metrics" | "logs" | "traces";
type Availability = "checking" | "ready" | "unauthorized" | "unavailable";

const TABS: Array<{ id: Tab; label: string; hint: string; icon: typeof ScrollText }> = [
  { id: "metrics", label: "Chỉ số", hint: "Bảng Grafana · số liệu Prometheus", icon: ChartNoAxesCombined },
  { id: "logs", label: "Nhật ký", hint: "Lượt chạy tác tử theo tác vụ", icon: ScrollText },
  { id: "traces", label: "Traces", hint: "Waterfall span của một lượt chạy", icon: Waypoints },
];

const RUN_STATUS: Record<string, { label: string; color: string }> = {
  running: { label: "Đang chạy", color: C.info },
  succeeded: { label: "Hoàn tất", color: C.ok },
  failed: { label: "Thất bại", color: C.risk },
  timeout: { label: "Quá hạn", color: C.warn },
};

const STEP_STATUS: Record<string, { label: string; color: string }> = {
  succeeded: { label: "OK", color: C.ok },
  failed: { label: "Lỗi", color: C.risk },
  timeout: { label: "Quá hạn", color: C.risk },
  partial: { label: "Một phần", color: C.warn },
};

function ms(iso: string): number {
  return new Date(iso).getTime();
}

function hms(iso: string): string {
  return formatDateTime(iso).slice(-8);
}

function runDuration(run: FcAgentRun): string {
  if (!run.finished_at) return "—";
  return duration(Math.max(0, ms(run.finished_at) - ms(run.started_at)));
}

function StatusPill({ status, map }: { status: string; map: Record<string, { label: string; color: string }> }) {
  const s = map[status] ?? { label: status, color: C.inkSoft };
  return (
    <span
      className="inline-flex flex-none items-center rounded-control px-1.5 py-0.5 text-3xs font-medium"
      style={{ background: `${s.color}1f`, color: s.color }}
    >
      {s.label}
    </span>
  );
}

// --- Nhật ký: lượt chạy tác tử như một log theo tác vụ, mở ra thấy từng bước ---

function RunSteps({ runId }: { runId: string }) {
  const detail = useApi(() => api.agentRun(runId), [runId]);
  if (detail.loading) return <Skeleton rows={2} />;
  if (detail.error) return <p className="px-3 py-2 text-2xs text-risk-soft">{detail.error}</p>;
  const steps = detail.data?.steps ?? [];
  if (!steps.length) return <p className="px-3 py-2 text-2xs text-ink-low">Lượt chạy này không gọi công cụ nào.</p>;
  return (
    <div className="space-y-1 border-t border-line-faint bg-app/40 px-3 py-2">
      {steps.map((s) => (
        <div key={s.id} className="flex items-start gap-2 font-mono text-3xs leading-relaxed">
          <span className="flex-none text-ink-dim">{hms(s.started_at)}</span>
          <span className="flex-none text-ink-low">{s.index}.</span>
          <StatusPill status={s.status} map={STEP_STATUS} />
          <span className="flex-none text-ink-hi">{s.tool}</span>
          <span className="flex-none text-ink-dim">{int(s.duration_ms)}ms</span>
          <span className="min-w-0 flex-1 truncate text-ink-soft" title={s.output_summary}>
            {s.output_summary}
          </span>
        </div>
      ))}
    </div>
  );
}

function LogsView() {
  const runs = useApi(() => api.agentRuns(), []);
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [open, setOpen] = useState<string | null>(null);

  const all = runs.data?.rows ?? [];
  const failed = all.filter((r) => r.status === "failed" || r.status === "timeout").length;
  const running = all.filter((r) => r.status === "running").length;
  const list = errorsOnly ? all.filter((r) => r.status === "failed" || r.status === "timeout") : all;

  if (runs.loading) return <Skeleton rows={6} />;
  if (runs.error) return <p className="px-4 py-6 text-sm text-risk-soft">{runs.error}</p>;
  if (!all.length) return <Empty text="Chưa có lượt chạy tác tử nào" hint="Chạy một bước điều tra để sinh nhật ký." />;

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5 text-2xs">
        <span className="text-ink-low">
          {int(all.length)} tác vụ · <span style={{ color: C.risk }}>{failed} lỗi</span> ·{" "}
          <span style={{ color: C.info }}>{running} đang chạy</span>
        </span>
        <label className="ml-auto inline-flex cursor-pointer items-center gap-1.5 text-ink-mid">
          <input type="checkbox" checked={errorsOnly} onChange={(e) => setErrorsOnly(e.target.checked)} />
          Chỉ lỗi
        </label>
      </div>
      <div className="divide-y divide-line-faint">
        {list.map((r) => {
          const isOpen = open === r.id;
          return (
            <div key={r.id}>
              <button
                type="button"
                onClick={() => setOpen(isOpen ? null : r.id)}
                className="flex w-full items-center gap-2.5 px-4 py-2 text-left transition-colors hover:bg-elev"
              >
                <span className="flex-none font-mono text-3xs text-ink-dim">{hms(r.started_at)}</span>
                <StatusPill status={r.status} map={RUN_STATUS} />
                <span className="flex-none text-2xs font-medium text-ink-hi">{agentLabel(r.tier)}</span>
                <span className="min-w-0 flex-1 truncate text-2xs text-ink-soft" title={r.conclusion}>
                  {r.conclusion || "—"}
                </span>
                <span className="flex-none font-mono text-3xs text-ink-low">{r.step_count} bước</span>
                <span className="flex-none font-mono text-3xs text-ink-low">{runDuration(r)}</span>
                <span className="hidden flex-none font-mono text-3xs text-ink-dim sm:inline">
                  {r.confidence != null ? conf(r.confidence) : ""}
                </span>
              </button>
              {isOpen && <RunSteps runId={r.id} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- Traces: waterfall span của một lượt chạy ---

function TraceWaterfall({ runId }: { runId: string }) {
  const detail = useApi(() => api.agentRun(runId), [runId]);
  const steps = detail.data?.steps ?? [];

  const layout = useMemo(() => {
    if (!steps.length) return null;
    const starts = steps.map((s) => ms(s.started_at));
    const t0 = Math.min(...starts);
    const total = Math.max(1, ...steps.map((s, i) => starts[i] - t0 + Math.max(1, s.duration_ms)));
    return { t0, total };
  }, [steps]);

  if (detail.loading) return <Skeleton rows={5} />;
  if (detail.error) return <p className="px-4 py-6 text-sm text-risk-soft">{detail.error}</p>;
  if (!steps.length || !layout)
    return <Empty text="Lượt chạy này không có span nào" hint="Chọn lượt chạy khác có gọi công cụ." />;

  return (
    <div className="space-y-1.5 p-3">
      <div className="mb-1 font-mono text-3xs text-ink-dim">tổng span {int(layout.total)}ms</div>
      {steps.map((s) => {
        const start = ms(s.started_at) - layout.t0;
        const left = (start / layout.total) * 100;
        const width = Math.max(1.5, (Math.max(1, s.duration_ms) / layout.total) * 100);
        const color = (STEP_STATUS[s.status] ?? { color: C.inkSoft }).color;
        return (
          <div key={s.id} className="flex items-center gap-2">
            <span className="w-40 flex-none truncate font-mono text-3xs text-ink-soft" title={s.tool}>
              {s.index}. {s.tool}
            </span>
            <div className="relative h-4 min-w-0 flex-1 rounded bg-app/50">
              <div
                className="absolute top-0 h-4 rounded"
                style={{ left: `${left}%`, width: `${width}%`, background: color }}
                title={`${s.status} · ${int(s.duration_ms)}ms`}
              />
            </div>
            <span className="w-14 flex-none text-right font-mono text-3xs text-ink-low">{int(s.duration_ms)}ms</span>
          </div>
        );
      })}
    </div>
  );
}

function TracesView() {
  const runs = useApi(() => api.agentRuns(), []);
  const [sel, setSel] = useState<string | null>(null);

  const all = runs.data?.rows ?? [];
  const active = sel ?? all[0]?.id ?? null;

  if (runs.loading) return <Skeleton rows={6} />;
  if (runs.error) return <p className="px-4 py-6 text-sm text-risk-soft">{runs.error}</p>;
  if (!all.length) return <Empty text="Chưa có lượt chạy tác tử nào" hint="Chạy một bước điều tra để sinh trace." />;

  return (
    <div className="grid md:grid-cols-[240px_1fr]">
      <div className="max-h-[520px] overflow-y-auto border-b border-line md:border-b-0 md:border-r">
        {all.map((r) => (
          <button
            key={r.id}
            type="button"
            onClick={() => setSel(r.id)}
            className={`flex w-full items-center gap-2 px-3 py-2 text-left text-2xs transition-colors hover:bg-elev ${
              r.id === active ? "bg-elev" : ""
            }`}
          >
            <StatusPill status={r.status} map={RUN_STATUS} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-ink-hi">{agentLabel(r.tier)}</span>
              <span className="block font-mono text-3xs text-ink-dim">
                {hms(r.started_at)} · {r.step_count} span
              </span>
            </span>
          </button>
        ))}
      </div>
      {active ? <TraceWaterfall runId={active} /> : <Empty text="Chọn một lượt chạy" hint="" />}
    </div>
  );
}

// --- Chỉ số: bảng Grafana (nhúng), CHỈ metrics ---

function MetricsView() {
  const [availability, setAvailability] = useState<Availability>("checking");
  const [reloadKey, setReloadKey] = useState(0);
  const [board, setBoard] = useState<BoardId>("system");
  const boardHref = boardUrl(board);

  const probe = useCallback(async () => {
    setAvailability("checking");
    try {
      const res = await fetch("/grafana/api/health", { cache: "no-store", credentials: "same-origin" });
      if (res.ok) setAvailability("ready");
      else if (res.status === 401 || res.status === 403) setAvailability("unauthorized");
      else setAvailability("unavailable");
    } catch {
      setAvailability("unavailable");
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe, reloadKey]);

  return (
    <div>
      <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-2xs text-ink-low">
        <div className="flex items-center gap-1" role="tablist" aria-label="Chọn bảng số liệu">
          {GRAFANA_BOARDS.map((b) => (
            <button
              key={b.id}
              type="button"
              role="tab"
              aria-selected={board === b.id}
              onClick={() => setBoard(b.id)}
              className={`h-7 rounded-control px-2.5 text-2xs ${
                board === b.id
                  ? "border border-accent-line bg-raised text-ink-hi"
                  : "border border-transparent text-ink-low hover:text-ink-mid"
              }`}
            >
              {b.label}
            </button>
          ))}
        </div>
        <span>Grafana chỉ để trực quan hoá số liệu (Prometheus) — logs/traces ở tab riêng.</span>
        <button type="button" className="fc-btn ml-auto h-7" onClick={() => setReloadKey((v) => v + 1)}>
          <RefreshCw size={12} aria-hidden /> Tải lại
        </button>
        <a className="fc-btn h-7" href={boardHref} target="_blank" rel="noreferrer">
          Mở Grafana <ExternalLink size={12} aria-hidden />
        </a>
      </div>
      {availability === "checking" && (
        <div className="grid min-h-[360px] place-items-center p-8 text-xs text-ink-low">Đang nối tới Grafana…</div>
      )}
      {availability === "unauthorized" && (
        <div className="grid min-h-[360px] place-items-center p-8 text-center text-xs text-ink-low">
          Phiên Grafana chưa xác thực — đăng xuất rồi đăng nhập lại FIN-07.
        </div>
      )}
      {availability === "unavailable" && (
        <div className="grid min-h-[360px] place-items-center p-8 text-center text-xs text-ink-low">
          Observability profile chưa chạy. Chạy{" "}
          <code className="mx-1 rounded bg-sunken px-1.5 py-0.5 font-mono text-primary">make obs-up</code> rồi bấm Tải lại.
        </div>
      )}
      {availability === "ready" && (
        <iframe
          key={`${board}-${reloadKey}`}
          className="block h-[820px] w-full border-0 bg-app"
          src={boardHref}
          title="FIN-07 · Grafana metrics"
          loading="eager"
        />
      )}
    </div>
  );
}

export function ObservabilityPanel() {
  const [tab, setTab] = useState<Tab>("metrics");
  const active = TABS.find((t) => t.id === tab) ?? TABS[0];

  return (
    <section className="overflow-hidden rounded-panel border border-line bg-panel">
      <header className="px-4 pb-3 pt-4">
        <h2 className="m-0 text-lg font-semibold text-ink-hi">Giám sát vận hành</h2>
        <p className="m-0 text-2xs text-ink-low">{active.hint}</p>
      </header>

      <nav className="flex gap-1 border-y border-line bg-sunken/45 px-3 py-2" aria-label="Chế độ quan sát">
        {TABS.map((t) => {
          const Icon = t.icon;
          const selected = t.id === tab;
          return (
            <button
              key={t.id}
              type="button"
              aria-current={selected ? "page" : undefined}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 rounded-control px-3 py-1.5 text-xs font-medium transition-colors ${
                selected ? "bg-primary text-app" : "text-ink-low hover:bg-elev hover:text-ink-hi"
              }`}
            >
              <Icon size={13} aria-hidden />
              {t.label}
            </button>
          );
        })}
      </nav>

      {tab === "metrics" && <MetricsView />}
      {tab === "logs" && <LogsView />}
      {tab === "traces" && <TracesView />}
    </section>
  );
}
