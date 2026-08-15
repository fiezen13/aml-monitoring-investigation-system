import { Activity, ChartNoAxesCombined, ExternalLink, RefreshCw, ScrollText, Waypoints } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

const OVERVIEW_PATH =
  "/grafana/d/fin07-observability/fin-07-observability?orgId=1&from=now-6h&to=now&refresh=30s&theme=dark&kiosk=tv";

type Availability = "checking" | "ready" | "unauthorized" | "unavailable";
type CockpitView = "overview" | "logs" | "traces";
type ServiceName = "fin07-backend" | "fin07-worker";

const VIEWS: Array<{
  id: CockpitView;
  label: string;
  description: string;
  icon: typeof Activity;
}> = [
  {
    id: "overview",
    label: "Tổng quan",
    description: "6 tín hiệu đủ để nhận biết tầng đang gặp vấn đề",
    icon: ChartNoAxesCombined,
  },
  {
    id: "logs",
    label: "Nhật ký lỗi",
    description: "Loki Explore dành riêng cho warning và error",
    icon: ScrollText,
  },
  {
    id: "traces",
    label: "Traces",
    description: "Jaeger waterfall để xác định span gây failure",
    icon: Waypoints,
  },
];

function explorePath(view: Exclude<CockpitView, "overview">, service: ServiceName, investigation: string): string {
  const cleanInvestigation = investigation.trim().replace(/[^A-Za-z0-9_-]/g, "").slice(0, 128);
  const datasource = view === "logs" ? { type: "loki", uid: "loki" } : { type: "jaeger", uid: "jaeger" };
  const query =
    view === "logs"
      ? {
          refId: "A",
          datasource,
          editorMode: "code",
          expr: `{service_name="${service}"} | json | level=~"WARNING|ERROR|CRITICAL"${
            cleanInvestigation ? ` | investigation_id="${cleanInvestigation}"` : ""
          }`,
          queryType: "range",
        }
      : {
          refId: "A",
          datasource,
          queryType: "search",
          service,
          operation: "",
          tags: cleanInvestigation ? `error=true aml.investigation.id=${cleanInvestigation}` : "error=true",
          limit: 40,
        };
  const panes = {
    A: {
      datasource: datasource.uid,
      queries: [query],
      range: { from: "now-6h", to: "now" },
    },
  };
  const params = new URLSearchParams({
    panes: JSON.stringify(panes),
    schemaVersion: "1",
    orgId: "1",
    kiosk: "tv",
  });
  return `/grafana/explore?${params.toString()}`;
}

/** Metrics stay concise; logs and traces live in focused investigation views. */
export function GrafanaCockpit() {
  const [availability, setAvailability] = useState<Availability>("checking");
  const [view, setView] = useState<CockpitView>("overview");
  const [service, setService] = useState<ServiceName>("fin07-worker");
  const [investigationDraft, setInvestigationDraft] = useState("");
  const [investigation, setInvestigation] = useState("");
  const [reloadKey, setReloadKey] = useState(0);

  const probe = useCallback(async () => {
    setAvailability("checking");
    try {
      const response = await fetch("/grafana/api/health", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.ok) setAvailability("ready");
      else if (response.status === 401 || response.status === 403) setAvailability("unauthorized");
      else setAvailability("unavailable");
    } catch {
      setAvailability("unavailable");
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe, reloadKey]);

  const activePath = useMemo(
    () => (view === "overview" ? OVERVIEW_PATH : explorePath(view, service, investigation)),
    [view, service, investigation],
  );
  const activeView = VIEWS.find((item) => item.id === view) ?? VIEWS[0];
  const reload = () => setReloadKey((value) => value + 1);

  return (
    <section className="overflow-hidden rounded-panel border border-line bg-panel">
      <header className="flex flex-wrap items-center gap-3 px-4 pb-3 pt-4">
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <span className="grid size-8 flex-none place-items-center rounded-control bg-primary/10 text-primary">
            <Activity size={16} aria-hidden />
          </span>
          <div className="min-w-0">
            <h2 className="m-0 text-lg font-semibold text-ink-hi">Giám sát vận hành</h2>
            <p className="m-0 text-2xs text-ink-low">{activeView.description}</p>
          </div>
        </div>
        <button type="button" className="fc-btn inline-flex items-center gap-1.5" onClick={reload}>
          <RefreshCw size={13} aria-hidden />
          Tải lại
        </button>
        <a className="fc-btn inline-flex items-center gap-1.5" href={activePath} target="_blank" rel="noreferrer">
          Mở rộng
          <ExternalLink size={13} aria-hidden />
        </a>
      </header>

      <nav className="flex gap-1 border-y border-line bg-sunken/45 px-3 py-2" aria-label="Chế độ quan sát">
        {VIEWS.map((item) => {
          const Icon = item.icon;
          const selected = item.id === view;
          return (
            <button
              key={item.id}
              type="button"
              aria-current={selected ? "page" : undefined}
              onClick={() => setView(item.id)}
              className={`inline-flex items-center gap-1.5 rounded-control px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 ${
                selected ? "bg-primary text-app" : "text-ink-low hover:bg-elev hover:text-ink-hi"
              }`}
            >
              <Icon size={13} aria-hidden />
              {item.label}
            </button>
          );
        })}
      </nav>

      {view !== "overview" && (
        <div className="flex flex-wrap items-end gap-3 border-b border-line px-4 py-3">
          <label className="grid gap-1 text-2xs text-ink-low">
            Dịch vụ
            <select
              value={service}
              onChange={(event) => setService(event.target.value as ServiceName)}
              className="h-8 rounded-control border border-line bg-elev px-2.5 text-xs text-ink-hi outline-none focus:border-primary"
            >
              <option value="fin07-worker">Worker · agent/Gemini</option>
              <option value="fin07-backend">Backend · API</option>
            </select>
          </label>
          <label className="grid min-w-64 flex-1 gap-1 text-2xs text-ink-low">
            Investigation ID <span className="sr-only">không bắt buộc</span>
            <input
              value={investigationDraft}
              onChange={(event) => setInvestigationDraft(event.target.value.replace(/[^A-Za-z0-9_-]/g, ""))}
              onKeyDown={(event) => {
                if (event.key === "Enter") setInvestigation(investigationDraft);
              }}
              placeholder="Để trống để xem mọi failure"
              className="h-8 rounded-control border border-line bg-elev px-2.5 font-mono text-xs text-ink-hi outline-none placeholder:text-ink-dim focus:border-primary"
            />
          </label>
          <button
            type="button"
            className="fc-btn h-8"
            onClick={() => setInvestigation(investigationDraft)}
          >
            Áp dụng
          </button>
          <span className="pb-2 text-2xs text-ink-dim">6 giờ gần nhất</span>
        </div>
      )}

      {availability === "checking" && (
        <div className="grid min-h-[420px] place-items-center p-8" aria-live="polite">
          <div className="text-center">
            <div className="mx-auto mb-3 h-1 w-28 overflow-hidden rounded-full bg-elev">
              <div className="h-full w-1/2 animate-pulse rounded-full bg-primary" />
            </div>
            <p className="text-xs text-ink-low">Đang nối tới Grafana…</p>
          </div>
        </div>
      )}

      {availability === "unauthorized" && (
        <div className="grid min-h-[420px] place-items-center p-8 text-center">
          <div className="max-w-md">
            <h3 className="text-lg font-semibold text-ink-hi">Phiên quan sát chưa được xác thực</h3>
            <p className="mt-2 text-xs leading-relaxed text-ink-low">
              Đăng xuất rồi đăng nhập lại FIN-07 để đồng bộ quyền Viewer của Grafana.
            </p>
          </div>
        </div>
      )}

      {availability === "unavailable" && (
        <div className="grid min-h-[420px] place-items-center p-8 text-center">
          <div className="max-w-md">
            <h3 className="text-lg font-semibold text-ink-hi">Observability profile chưa chạy</h3>
            <p className="mt-2 text-xs leading-relaxed text-ink-low">
              Chạy <code className="rounded bg-sunken px-1.5 py-0.5 font-mono text-primary">make obs-up</code>, rồi bấm
              Tải lại.
            </p>
          </div>
        </div>
      )}

      {availability === "ready" && (
        <iframe
          key={`${view}-${reloadKey}`}
          className={`block w-full border-0 bg-app ${view === "overview" ? "h-[900px]" : "h-[980px]"}`}
          src={activePath}
          title={`FIN-07 ${activeView.label}`}
          loading="eager"
        />
      )}
    </section>
  );
}
