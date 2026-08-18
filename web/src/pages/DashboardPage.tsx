import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { int } from "../api/fcFormat";
import { alertStatusLabel, detectorLabel, formatRelative } from "../api/format";
import { useApi } from "../api/useApi";
import { Chart, type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import {
  Badge,
  CardSkeleton,
  Column,
  DataTable,
  MetricCard,
  Panel,
  PageShell,
  PulseDot,
  RiskIndicator,
} from "../components/ui";
import { ALERT_STATUS_TONE, DETECTOR_TONE, type Tone } from "../design/semantic";
import { SERIES, toneColor } from "../design";
import type { ApiAlert } from "../api/client";

/**
 * Tổng quan giám sát — màn hình mặc định và bản mẫu tham chiếu của hệ thiết kế.
 *
 * Mọi trang khác nên đọc file này trước khi tự phát minh bố cục: hàng KPI dùng
 * `MetricCard`, khối nội dung dùng `Panel`, bảng dùng `DataTable`, khoảng cách
 * và bề rộng do `PageShell` quyết định. Không có `p-4` hay `max-w-[1280px]` viết
 * tay ở đây, và không có một mã hex nào.
 *
 * Thứ tự đọc: hàng KPI để liếc một cái là nắm tình hình → biểu đồ xu hướng →
 * hàng đợi ưu tiên, thứ analyst thực sự phải làm gì đó với nó.
 */

export function DashboardPage() {
  const navigate = useNavigate();
  const dashboard = useApi(() => api.dashboard(), []);
  const world = useApi(() => api.world(), []);

  const d = dashboard.data;

  const kpis = useMemo(() => {
    if (!d) return [];
    const normalPct = Math.round((d.subjects_below_threshold / Math.max(1, d.subjects_analyzed)) * 1000) / 10;
    const triggeredPct = Math.round((d.subjects_triggered / Math.max(1, d.subjects_analyzed)) * 1000) / 10;
    return [
      {
        // "đã chấm điểm", KHÔNG phải "đã nạp": con số này là
        // `edge_model_release.transaction_rows`, tức tập mà mô hình thật sự chấm
        // — không phải số dòng trong bảng `transaction`. Hai con số lệch nhau
        // hẳn (6,75 triệu so với 18,5 triệu) vì cơ sở dữ liệu còn giữ lịch sử
        // ngoài tập đánh giá. Nhãn cũ khiến người đọc tưởng đã mất dữ liệu.
        //
        // Ba ô ở đây phải cộng đúng: dưới ngưỡng + vượt ngưỡng = đã chấm điểm.
        label: "Giao dịch đã chấm điểm",
        value: d.transactions_analyzed,
        tone: "neutral" as Tone,
        note: d.latest_source_name ?? "chưa có lô dữ liệu",
      },
      {
        label: "Dưới ngưỡng",
        value: d.subjects_below_threshold,
        tone: "ok" as Tone,
        note: `${normalPct}% giao dịch được chấm`,
      },
      {
        label: "Vượt ngưỡng",
        value: d.subjects_triggered,
        tone: "warn" as Tone,
        note: `${triggeredPct}% giao dịch được chấm`,
      },
      {
        // Phải là hàng đợi thật, không phải số giao dịch vượt ngưỡng của mô hình
        // cạnh: hai con số đó khác nhau và nhãn "Cảnh báo" thì người đọc luôn
        // hiểu là hàng đợi. Trước đây thẻ này hiện `batch_alerts_created`, vốn
        // trùng y hệt thẻ "Vượt ngưỡng" bên cạnh và lệch hẳn với Trung tâm cảnh
        // báo — mô hình cạnh chấm điểm giao dịch nhưng không sinh cảnh báo nào.
        label: "Cảnh báo chưa xử lý",
        value: d.open_alerts,
        tone: "risk" as Tone,
        note: "từ ba nhánh: luật, bất thường, đồ thị",
      },
      {
        label: "Vụ việc đang xử lý",
        value: d.cases_investigating,
        tone: "agent" as Tone,
        note: "chưa kết luận",
      },
      {
        label: "Hàng lệnh worker",
        value: d.queue_depth,
        tone: (d.worker_alive ? "ok" : "risk") as Tone,
        note: d.worker_alive ? "worker đang chạy" : "worker không phản hồi",
      },
    ];
  }, [d]);

  // Xu hướng dựng từ chính thời điểm tạo cảnh báo — số thật, không phải đường
  // cong minh hoạ.
  const trendSpec = useMemo<ChartSpec | null>(() => {
    if (!d?.top_alerts?.length) return null;
    const buckets = new Map<string, { total: number; high: number }>();
    for (const alert of d.top_alerts) {
      const key = new Date(alert.created_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
      const current = buckets.get(key) ?? { total: 0, high: 0 };
      current.total += 1;
      if (num(alert.risk_score) >= 80) current.high += 1;
      buckets.set(key, current);
    }
    const labels = [...buckets.keys()].reverse();
    return {
      type: "bars",
      labels,
      series: [
        { name: "Tổng cảnh báo", data: labels.map((l) => buckets.get(l)!.total), color: toneColor("info") },
        { name: "Rủi ro cao", data: labels.map((l) => buckets.get(l)!.high), color: toneColor("risk") },
      ],
    };
  }, [d]);

  const typologySpec = useMemo<ChartSpec | null>(() => {
    if (!d?.typology_distribution?.length) return null;
    return {
      type: "donut",
      items: d.typology_distribution.map((t, index) => ({
        label: t.typology_code,
        value: t.alert_count,
        color: SERIES[index % SERIES.length],
      })),
    };
  }, [d]);

  const corridorSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    const top = [...flows].sort((a, b) => b.risk_score - a.risk_score).slice(0, 6);
    return {
      type: "hbars",
      items: top.map((flow) => ({
        label: `${flow.source_name} → ${flow.target_name}`,
        value: Math.round(flow.volume_usd / 1e6),
        color: toneColor(flow.risk_score >= 80 ? "risk" : flow.risk_score >= 60 ? "warn" : "ok"),
        sub: `${flow.channel} · rủi ro ${flow.risk_score}`,
      })),
    };
  }, [world.data]);

  const queueColumns: Column<ApiAlert>[] = [
    {
      key: "alert_id",
      header: "Cảnh báo",
      render: (alert) => (
        <span className="tabular whitespace-nowrap font-mono text-data text-primary">{alert.alert_id}</span>
      ),
    },
    {
      key: "account",
      header: "Tài khoản",
      render: (alert) => <span className="truncate-1 tabular font-mono text-data">{alert.account_key}</span>,
    },
    {
      key: "typology",
      header: "Nhóm hành vi",
      render: (alert) => (
        <span className="truncate-1 block max-w-[180px] text-ink-soft" title={alert.typology_label}>
          {alert.typology_label}
        </span>
      ),
    },
    {
      key: "risk",
      header: "Rủi ro",
      sortValue: (alert) => num(alert.risk_score),
      render: (alert) => <RiskIndicator score={num(alert.risk_score)} />,
    },
    {
      key: "detector",
      header: "Bộ phát hiện",
      render: (alert) => (
        <Badge tone={DETECTOR_TONE[alert.detector] ?? "neutral"} icon={false}>
          {detectorLabel(alert.detector)}
        </Badge>
      ),
    },
    {
      key: "created",
      header: "Tạo lúc",
      sortValue: (alert) => alert.created_at,
      render: (alert) => <span className="text-ink-soft">{formatRelative(alert.created_at)}</span>,
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (alert) => (
        <Badge tone={ALERT_STATUS_TONE[alert.status] ?? "neutral"}>{alertStatusLabel(alert.status)}</Badge>
      ),
    },
  ];

  return (
    <PageShell
      variant="dense"
      subtitle={
        <>
          Lô dữ liệu {d?.latest_source_name ?? "chưa có nguồn"} · toàn bộ số liệu dưới đây là tổng của một lượt chạy,
          không phải chuỗi thời gian
        </>
      }
    >
      {dashboard.error && (
        <div className="rounded-panel border border-risk/40 bg-risk/10 px-4 py-2.5 text-data text-risk-soft" role="alert">
          {dashboard.error}
        </div>
      )}

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(168px,1fr))" }}>
        {dashboard.loading && !d ? (
          <CardSkeleton count={6} height={84} />
        ) : (
          kpis.map((kpi) => (
            <MetricCard key={kpi.label} label={kpi.label} value={kpi.value} tone={kpi.tone} note={kpi.note} />
          ))
        )}
      </div>

      <div className="flex flex-wrap items-start gap-3.5">
        <div className="flex min-w-0 flex-[2.4_1_520px] flex-col gap-3.5">
          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            <ChartCard
              title="5 cảnh báo ưu tiên theo ngày"
              subtitle="Chỉ gồm nhóm cảnh báo ưu tiên, không phải phân phối của toàn bộ giao dịch"
              spec={trendSpec}
              state={dashboard.loading ? "loading" : trendSpec ? "ok" : "empty"}
              note="Nguồn: bảng cảnh báo · điểm hiện tại là điểm bất thường của ML hành vi, không phải xác suất rửa tiền."
            />
            <ChartCard
              title="Hành lang địa lý"
              subtitle="Chỉ hiển thị khi nguồn có quốc gia/toạ độ đã kiểm chứng"
              spec={corridorSpec}
              tools={["data", "dl", "full"]}
              state={world.loading ? "loading" : corridorSpec ? "ok" : "empty"}
            />
          </div>

          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            <Panel title="Nhóm hành vi gợi ý" subtitle="Gợi ý trên tập cảnh báo, chưa phải kết luận điều tra">
              <div className="flex items-center gap-3">
                <div className="w-[118px] flex-none">
                  <Chart spec={typologySpec} height={118} />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1.5 text-data">
                  {d?.typology_distribution.map((typology, index) => (
                    <div key={typology.typology_code} className="flex items-center gap-1.5 overflow-hidden">
                      <span
                        className="h-2 w-2 flex-none rounded-sm"
                        style={{ background: SERIES[index % SERIES.length] }}
                        aria-hidden
                      />
                      <span className="truncate-1 text-ink-soft" title={typology.typology_label}>
                        {typology.typology_label}
                      </span>
                      <b className="tabular ml-auto font-mono text-ink-hi">{typology.alert_count}</b>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          </div>

          <Panel
            title="Hàng đợi ưu tiên — cần xử lý trước"
            padded={false}
            actions={
              <Link
                to="/alerts"
                className="text-data text-info-soft transition-colors hover:text-info"
              >
                Mở Trung tâm cảnh báo →
              </Link>
            }
          >
            <DataTable
              columns={queueColumns}
              rows={d?.top_alerts ?? []}
              rowKey={(alert) => alert.alert_id}
              onRowClick={(alert) => navigate(`/alerts/${alert.alert_id}`)}
              loading={dashboard.loading && !d}
              minWidth={760}
              dense
              emptyTitle="Hàng đợi trống"
              emptyDetail="Không có cảnh báo nào đang chờ xử lý trong lô dữ liệu hiện tại."
            />
          </Panel>
        </div>

        <div className="flex min-w-0 max-w-[420px] flex-[1_1_320px] flex-col gap-3.5">
          <Panel title="Tình hình dòng tiền" subtitle="Tổng hợp từ Giám sát địa lý">
            {world.loading && <div className="h-24 animate-pulse rounded-control bg-elev/60" aria-hidden />}
            {world.data?.geography_available && (
              <div className="flex flex-col gap-2">
                {[...world.data.hubs]
                  .sort((a, b) => b.inbound + b.outbound - (a.inbound + a.outbound))
                  .slice(0, 6)
                  .map((hub) => (
                    <div key={hub.id} className="flex items-center gap-2 text-data">
                      <span className="truncate-1 flex-1 text-ink-mid">{hub.name}</span>
                      <span className="tabular flex-none font-mono text-meta text-ink-low">
                        {hub.inbound}↓ {hub.outbound}↑
                      </span>
                      <b className="tabular w-24 flex-none text-right font-mono text-ink-hi">
                        {int(hub.inbound + hub.outbound)} GD
                      </b>
                    </div>
                  ))}
                <Link
                  to="/world"
                  className="mt-1 text-center text-data text-info-soft transition-colors hover:text-info"
                >
                  Mở Giám sát địa lý →
                </Link>
              </div>
            )}
            {world.data && !world.data.geography_available && (
              <div className="rounded-control border border-warn/25 bg-warn/10 p-3">
                <div className="text-data font-semibold text-warn-soft">Chưa có dữ liệu địa lý đã kiểm chứng</div>
                <p className="mt-1.5 text-meta leading-relaxed text-ink-soft">{world.data.limitation}</p>
                <div className="mt-3 flex items-center justify-between gap-2 text-meta">
                  <span className="font-mono text-ink-mid">
                    {int(world.data.transaction_count)} giao dịch · {world.data.source_name ?? "chưa có nguồn"}
                  </span>
                  <Link to="/world" className="text-info-soft transition-colors hover:text-info">
                    Xem nguồn →
                  </Link>
                </div>
              </div>
            )}
          </Panel>

          <Panel
            title={
              <span className="flex items-center gap-2">
                <PulseDot tone="primary" size={6} />
                Trạng thái hệ thống
              </span>
            }
          >
            <dl className="flex flex-col gap-2 text-data">
              {[
                ["Chế độ dữ liệu", world.data?.data_mode === "operational" ? "vận hành" : "mô phỏng"],
                ["Nguồn giao dịch", world.data?.source_name ?? "—"],
                ["Giao dịch đã chấm điểm", world.data ? int(world.data.transaction_count) : "—"],
                ["Dữ liệu địa lý", world.data?.geography_available ? "có" : "chưa có"],
                ["Worker nền", d?.worker_alive ? "đang chạy" : "không phản hồi"],
                ["Chiều sâu hàng lệnh", d ? String(d.queue_depth) : "—"],
              ].map(([key, value]) => (
                <div key={key} className="flex items-center gap-2">
                  <dt className="flex-1 text-ink-low">{key}</dt>
                  <dd className="tabular font-mono text-ink-mid">{value}</dd>
                </div>
              ))}
            </dl>
          </Panel>

          <Panel title="Giới hạn cần biết" subtitle="Công bố kèm mọi kết quả">
            <p className="text-meta leading-relaxed text-ink-soft">
              ML đang phục vụ release {d?.latest_source_name ?? "chưa xác định"}. Bản đồ dùng bảng tham chiếu
              bank-country của dự án;
              một phần quốc gia được gán cho ngân hàng hư cấu và không phải dữ liệu pháp vực từ IBM. Không dùng bản đồ
              để kết luận thẩm quyền pháp lý hoặc cộng giá trị giữa các currency.
            </p>
            <p className="mt-2 text-meta leading-relaxed text-ink-low">
              Không có thiết kế dataset nào bảo đảm phát hiện đầy đủ giao dịch tiền mặt hoặc tài sản ẩn danh không đi
              qua điểm chuyển đổi vào/ra tài sản quan sát được.
            </p>
          </Panel>
        </div>
      </div>
    </PageShell>
  );
}
