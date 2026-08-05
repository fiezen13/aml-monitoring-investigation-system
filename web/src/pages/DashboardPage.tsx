import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { usd } from "../api/fcFormat";
import { formatRelative } from "../api/format";
import { useApi } from "../api/useApi";
import { Chart, type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { Empty, KpiCard, Panel, PulseDot, RiskScore, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { useConsole, WINDOW_LABEL } from "../context/ConsoleContext";
import { C, SERIES } from "../design/palette";

/**
 * Tổng quan giám sát — màn hình mặc định.
 *
 * Bố cục theo prototype: hàng KPI trên cùng để liếc một cái là nắm tình hình,
 * rồi tới biểu đồ xu hướng, cuối cùng là hàng đợi ưu tiên — thứ analyst thực
 * sự phải làm gì đó với nó.
 */

const QUEUE_COLS = "112px minmax(140px,1fr) 150px 92px 84px 100px 110px";

export function DashboardPage() {
  const navigate = useNavigate();
  const { window: win } = useConsole();
  const dashboard = useApi(() => api.dashboard(), []);
  const world = useApi(() => api.world(), []);
  const benchmarks = useApi(() => api.benchmarks(), []);

  const d = dashboard.data;

  const kpis = useMemo(() => {
    if (!d) return [];
    return [
      { label: "Cảnh báo đang mở", value: d.open_alerts, color: C.inkHi, delta: "trong hàng đợi" },
      {
        label: "Rủi ro cao (≥80)",
        value: d.high_risk_alerts,
        color: C.risk,
        delta: `${Math.round((d.high_risk_alerts / Math.max(1, d.open_alerts)) * 100)}% hàng đợi`,
      },
      { label: "Vụ việc đang xử lý", value: d.cases_investigating, color: C.warn, delta: "chưa kết luận" },
      { label: "SAR chờ duyệt", value: d.sar_pending, color: C.agent, delta: "cần người có thẩm quyền" },
      { label: "Điểm rủi ro trung bình", value: d.avg_risk_score, color: C.info, delta: "trên toàn hàng đợi" },
      {
        label: "Hàng lệnh worker",
        value: d.queue_depth,
        color: d.worker_alive ? C.ok : C.risk,
        delta: d.worker_alive ? "worker đang chạy" : "worker không phản hồi",
      },
    ];
  }, [d]);

  // Xu hướng dựng từ chính thời điểm tạo cảnh báo — số thật, không phải đường
  // cong minh hoạ.
  const trendSpec = useMemo<ChartSpec | null>(() => {
    if (!d?.top_alerts?.length) return null;
    const buckets = new Map<string, { total: number; high: number }>();
    for (const a of d.top_alerts) {
      const key = new Date(a.created_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
      const cur = buckets.get(key) ?? { total: 0, high: 0 };
      cur.total += 1;
      if (num(a.risk_score) >= 80) cur.high += 1;
      buckets.set(key, cur);
    }
    const labels = [...buckets.keys()].reverse();
    return {
      type: "bars",
      labels,
      series: [
        { name: "Tổng cảnh báo", data: labels.map((l) => buckets.get(l)!.total), color: C.info },
        { name: "Rủi ro cao", data: labels.map((l) => buckets.get(l)!.high), color: C.risk },
      ],
    };
  }, [d]);

  const typologySpec = useMemo<ChartSpec | null>(() => {
    if (!d?.typology_distribution?.length) return null;
    return {
      type: "donut",
      items: d.typology_distribution.map((t, i) => ({
        label: t.typology_code,
        value: t.alert_count,
        color: SERIES[i % SERIES.length],
      })),
    };
  }, [d]);

  const corridorSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const top = [...flows].sort((a, b) => b.risk_score - a.risk_score).slice(0, 6);
    return {
      type: "hbars",
      items: top.map((f) => ({
        label: `${f.source_name} → ${f.target_name}`,
        value: Math.round(f.volume_usd / 1e6),
        color: f.risk_score >= 80 ? C.risk : f.risk_score >= 60 ? C.warn : C.ok,
        sub: `${f.channel} · risk ${f.risk_score}`,
      })),
    };
  }, [world.data]);

  const benchSpec = useMemo<ChartSpec | null>(() => {
    const rows = benchmarks.data;
    if (!rows?.length) return null;
    // Chỉ lấy chỉ số thang 0–1 để một trục chung còn có nghĩa; lead time tính
    // bằng ngày nên để riêng ở màn hình Benchmarks.
    const ratio = rows.filter((r) => r.metric_value <= 1 && r.target_value != null);
    if (!ratio.length) return null;
    return {
      type: "bars",
      labels: ratio.map((r) => r.metric_name.replace(/_/g, " ").slice(0, 18)),
      series: [
        { name: "Đạt được", data: ratio.map((r) => r.metric_value), color: C.primary },
        { name: "Ngưỡng yêu cầu", data: ratio.map((r) => r.target_value!), color: C.inkDim },
      ],
    };
  }, [benchmarks.data]);

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
      <ScreenTitle
        title="Tổng quan giám sát"
        meta={
          <>
            Cửa sổ {WINDOW_LABEL[win]} · dữ liệu synthetic
            {world.data?.scenario_package ? ` · kịch bản ${world.data.scenario_package}` : ""}
          </>
        }
      />

      {dashboard.error && (
        <div className="rounded-panel border border-risk/40 bg-risk/10 px-3.5 py-2.5 text-sm text-risk-soft">
          {dashboard.error}
        </div>
      )}

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(168px,1fr))" }}>
        {dashboard.loading && !d
          ? Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-[76px] animate-pulse rounded-panel bg-panel" />
            ))
          : kpis.map((k) => (
              <KpiCard key={k.label} label={k.label} value={k.value} valueColor={k.color} delta={k.delta} />
            ))}
      </div>

      <div className="flex flex-wrap items-start gap-3.5">
        <div className="flex min-w-0 flex-[2.4_1_520px] flex-col gap-3.5">
          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            <ChartCard
              title="Cảnh báo theo ngày"
              subtitle="Tổng · rủi ro cao · kéo để phóng to, nháy đúp để đặt lại"
              spec={trendSpec}
              state={dashboard.loading ? "loading" : trendSpec ? "ok" : "empty"}
              note="Nguồn: bảng alert · điểm số do Risk Fusion chấm"
            />
            <ChartCard
              title="Hành lang rủi ro nhất"
              subtitle="Khối lượng (triệu USD), tô màu theo mức rủi ro"
              spec={corridorSpec}
              tools={["data", "dl", "full"]}
              state={world.loading ? "loading" : corridorSpec ? "ok" : "empty"}
            />
          </div>

          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            <ChartCard
              title="Kiểm định mô hình"
              subtitle="Chỉ số đạt được so với ngưỡng đặt trước"
              height={176}
              spec={benchSpec}
              tools={["data", "dl", "full"]}
              state={benchmarks.loading ? "loading" : benchSpec ? "ok" : "empty"}
              note="Không dùng accuracy làm chỉ số chính — xem màn hình Benchmarks."
            />
            <Panel title="Phân bố typology" subtitle="Theo số cảnh báo đang mở">
              <div className="flex items-center gap-3">
                <div className="w-[118px] flex-none">
                  <Chart spec={typologySpec} height={118} />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1.5 text-xs">
                  {d?.typology_distribution.map((t, i) => (
                    <div key={t.typology_code} className="flex items-center gap-1.5 overflow-hidden">
                      <span
                        className="h-2 w-2 flex-none rounded-sm"
                        style={{ background: SERIES[i % SERIES.length] }}
                      />
                      <span className="truncate-1 text-ink-soft" title={t.typology_label}>
                        {t.typology_label}
                      </span>
                      <b className="tabular ml-auto font-mono">{t.alert_count}</b>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          </div>

          <Panel
            title="Hàng đợi ưu tiên — cần xử lý trước"
            actions={
              <Link to="/alerts" className="text-sm text-primary hover:text-primary-hover">
                Mở Alert Center →
              </Link>
            }
            bodyClassName="overflow-x-auto"
          >
            <div className="min-w-[720px]">
              <div
                className="grid gap-2 border-b border-line px-2 py-1.5 text-3xs uppercase tracking-[0.07em] text-ink-low"
                style={{ gridTemplateColumns: QUEUE_COLS }}
              >
                <span>Cảnh báo</span>
                <span>Tài khoản</span>
                <span>Typology</span>
                <span>Risk</span>
                <span>Detector</span>
                <span>Tạo lúc</span>
                <span>Trạng thái</span>
              </div>
              {dashboard.loading && <Skeleton rows={5} />}
              {!dashboard.loading && !d?.top_alerts.length && <Empty text="Hàng đợi trống" />}
              {d?.top_alerts.map((a) => (
                <div
                  key={a.alert_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => navigate(`/alerts/${a.alert_id}`)}
                  onKeyDown={(e) => e.key === "Enter" && navigate(`/alerts/${a.alert_id}`)}
                  className="grid cursor-pointer items-center gap-2 border-b border-line-faint px-2 py-[7px] text-base transition-colors hover:bg-elev"
                  style={{ gridTemplateColumns: QUEUE_COLS }}
                >
                  <span className="font-mono text-xs text-primary">{a.alert_id}</span>
                  <span className="truncate-1 font-mono text-xs">{a.account_key}</span>
                  <span className="truncate-1 text-xs text-ink-soft" title={a.typology_label}>
                    {a.typology_label}
                  </span>
                  <RiskScore score={Math.round(num(a.risk_score))} />
                  <span className="text-xs text-ink-soft">{a.detector}</span>
                  <span className="text-xs text-ink-soft">{formatRelative(a.created_at)}</span>
                  <span className="text-2xs text-ink-soft">{a.status}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div className="flex min-w-0 max-w-[420px] flex-[1_1_320px] flex-col gap-3.5">
          <Panel title="Tình hình dòng tiền" subtitle="Tổng hợp từ World Monitor">
            {world.loading && <Skeleton rows={4} />}
            {world.data && (
              <div className="flex flex-col gap-2">
                {[...world.data.hubs]
                  .sort((a, b) => b.volume_usd - a.volume_usd)
                  .slice(0, 6)
                  .map((h) => (
                    <div key={h.id} className="flex items-center gap-2 text-xs">
                      <span className="truncate-1 flex-1 text-ink-mid">{h.name}</span>
                      <span className="tabular flex-none font-mono text-2xs text-ink-low">
                        {h.inbound}↓ {h.outbound}↑
                      </span>
                      <b className="tabular w-16 flex-none text-right font-mono">{usd(h.volume_usd)}</b>
                    </div>
                  ))}
                <Link to="/world" className="mt-1 text-center text-sm text-primary hover:text-primary-hover">
                  Mở World Monitor →
                </Link>
              </div>
            )}
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-2">
                <PulseDot color={C.primary} size={6} />
                Trạng thái hệ thống
              </span>
            }
          >
            <dl className="flex flex-col gap-2 text-xs">
              {[
                ["Lần chạy mô phỏng", world.data?.simulation_id ?? "—"],
                ["Gói kịch bản", world.data?.scenario_package ?? "—"],
                ["Trung tâm tài chính", world.data ? String(world.data.hubs.length) : "—"],
                ["Hành lang theo dõi", world.data ? String(world.data.flows.length) : "—"],
                ["Worker nền", d?.worker_alive ? "đang chạy" : "không phản hồi"],
                ["Chiều sâu hàng lệnh", d ? String(d.queue_depth) : "—"],
              ].map(([k, v]) => (
                <div key={k} className="flex items-center gap-2">
                  <dt className="flex-1 text-ink-low">{k}</dt>
                  <dd className="tabular font-mono text-ink-mid">{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          <Panel title="Giới hạn cần biết" subtitle="Công bố kèm mọi kết quả">
            <p className="text-xs leading-relaxed text-ink-soft">
              Toàn bộ dữ liệu ở đây là tổng hợp từ mô phỏng ABM. Nó đủ để dựng PoC và benchmark có căn cứ, nhưng{" "}
              <b className="text-ink-mid">chưa đủ để khẳng định mô hình sẵn sàng triển khai</b> — việc đó cần hiệu
              chỉnh và kiểm định trên dữ liệu thật đã được bảo vệ tại một tổ chức có thẩm quyền.
            </p>
            <p className="mt-2 text-xs leading-relaxed text-ink-low">
              Không có thiết kế dataset nào bảo đảm phát hiện đầy đủ giao dịch tiền mặt hoặc tài sản ẩn danh không đi
              qua điểm on/off-ramp quan sát được.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}
