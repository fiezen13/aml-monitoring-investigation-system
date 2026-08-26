import { useMemo, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { int } from "../api/fcFormat";
import { alertStatusLabel, datasetLabel, detectorLabel, formatRelative, sourceBrand } from "../api/format";
import { TYPOLOGY_LABELS } from "../api/typologyLabels";
import { useApi } from "../api/useApi";
import { useConsole } from "../context/ConsoleContext";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import {
  Badge,
  CardSkeleton,
  Column,
  DataTable,
  MetricCard,
  Panel,
  PageShell,
  ProgressBar,
  RiskIndicator,
} from "../components/ui";
import { ALERT_STATUS_TONE, DETECTOR_TONE, type Tone } from "../design/semantic";
import { toneColor } from "../design";
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

// Nhãn + tông màu cho phân bố rủi ro vụ việc. Để ngoài component để không vào
// deps của useMemo.
const BAND_META: Record<string, { label: string; tone: Tone }> = {
  critical: { label: "Nghiêm trọng", tone: "risk" },
  high: { label: "Cao", tone: "warn" },
  medium: { label: "Vừa", tone: "info" },
  low: { label: "Thấp", tone: "ok" },
};

export function DashboardPage() {
  const navigate = useNavigate();
  const { dataset } = useConsole();
  // `dataset` nằm trong deps: đổi bộ dữ liệu ở header thì Tổng quan hỏi lại
  // ngay, không còn cảnh thẻ số một bộ mà biểu đồ lại bộ khác.
  const dashboard = useApi(() => api.dashboard({ dataset }), [dataset], `dashboard:${dataset}`);
  const world = useApi(() => api.world(), [], "world");

  const d = dashboard.data;

  const kpis = useMemo<
    { label: string; value: ReactNode; tone: Tone; note: ReactNode; onClick?: () => void }[]
  >(() => {
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
        // Chỉ hiện thương hiệu nguồn ("IBM"), không lộ biến thể nội bộ
        // (LI-Small/HI-Medium) — người dùng không cần và dễ hiểu nhầm là chất lượng.
        note: d.latest_source_name ? sourceBrand(d.latest_source_name) : "chưa có dữ liệu",
      },
      {
        label: "Dưới ngưỡng",
        value: d.subjects_below_threshold,
        tone: "ok" as Tone,
        note: `${normalPct}% giao dịch được chấm`,
      },
      {
        // "Vượt ngưỡng" CHÍNH LÀ cảnh báo: mỗi giao dịch mô hình chấm quá ngưỡng
        // là một cảnh báo. Trước đây tách làm hai thẻ — "Vượt ngưỡng"
        // (triggered_rows của release đang xem) và "Cảnh báo chưa xử lý"
        // (đếm TOÀN bảng alert, cộng dồn mọi đợt chạy + mọi detector) — nên hai
        // con số lệch nhau vô lý (3.085 so với 10.415) dù đáng lẽ là một. Gộp lại,
        // lấy THEO RELEASE HIỆN TẠI: dưới ngưỡng + cảnh báo = đã chấm điểm, phễu
        // Tổng quan khớp trong một lô, không kéo tồn đọng của đợt cũ vào.
        label: "Cảnh báo",
        value: d.subjects_triggered,
        tone: "risk" as Tone,
        note: `${triggeredPct}% giao dịch vượt ngưỡng`,
      },
      {
        // Bấm vào để mở thẳng danh sách hồ sơ vụ việc — người dùng thấy con số
        // "đang xử lý" thì việc kế tiếp luôn là xem đó là những vụ nào.
        label: "Vụ việc đang xử lý",
        value: d.cases_investigating,
        tone: "agent" as Tone,
        note: "chưa kết luận · mở hồ sơ →",
        onClick: () => navigate("/cases"),
      },
      // Bỏ thẻ "Hàng lệnh worker": chiều sâu hàng đợi/trạng thái worker là việc
      // nội bộ của hệ thống, không phải chỉ số nghiệp vụ mà analyst cần theo dõi.
    ];
  }, [d, navigate]);

  // Phân bố RỦI RO vụ việc — trả lời trực tiếp "điểm rủi ro đang ở đâu", đếm
  // thật từ vụ việc đang mở (không phải điểm bất thường của 5 cảnh báo lẻ).
  const riskBandSpec = useMemo<ChartSpec | null>(() => {
    if (!d?.case_risk_bands?.length) return null;
    const total = d.case_risk_bands.reduce((s, b) => s + b.count, 0) || 1;
    return {
      type: "hbars",
      items: d.case_risk_bands.map((b) => ({
        label: BAND_META[b.band]?.label ?? b.band,
        value: b.count,
        color: toneColor(BAND_META[b.band]?.tone ?? "info"),
        sub: `${Math.round((b.count / total) * 100)}% số vụ đang mở`,
      })),
    };
  }, [d]);

  // Phễu xử lý (quản lý): Cảnh báo → Vụ việc → Chờ duyệt SAR, kèm tỉ lệ chuyển.
  const funnelSpec = useMemo<ChartSpec | null>(() => {
    if (!d) return null;
    const a = d.open_alerts;
    const c = d.cases_total;
    const s = d.sar_pending;
    if (a + c + s === 0) return null;
    return {
      type: "funnel",
      items: [
        { label: "Cảnh báo chưa đóng", value: a, color: toneColor("info") },
        {
          label: "Đã thành vụ việc",
          value: c,
          color: toneColor("warn"),
          pctOfPrev: a ? `${((c / a) * 100).toFixed(1)}%` : undefined,
        },
        {
          label: "Chờ duyệt SAR",
          value: s,
          color: toneColor("risk"),
          pctOfPrev: c ? `${((s / c) * 100).toFixed(1)}%` : undefined,
        },
      ],
    };
  }, [d]);

  // Xu hướng cảnh báo theo TUẦN trên cả cửa sổ dữ liệu — trend thật để bắt spike.
  const trendSpec = useMemo<ChartSpec | null>(() => {
    if (!d?.alert_trend?.length) return null;
    const labels = d.alert_trend.map((p) => {
      const [, m, day] = p.week.split("-");
      return `${day}/${m}`;
    });
    return {
      type: "bars",
      labels,
      series: [
        { name: "Tổng cảnh báo", data: d.alert_trend.map((p) => p.total), color: toneColor("info") },
        { name: "Rủi ro cao (≥80)", data: d.alert_trend.map((p) => p.high), color: toneColor("risk") },
      ],
    };
  }, [d]);

  // Hành lang NGUY HIỂM NHẤT: gộp các cạnh flow theo cặp quốc gia (một hành lang
  // xuất hiện nhiều cạnh), lấy điểm rủi ro cao nhất + cộng cảnh báo + nhóm hành
  // vi. Thay cho bảng "đếm lượt" cũ vốn chỉ là volume, không cho biết cái gì đáng
  // lo. (Ở mức QUỐC GIA không có tín hiệu rủi ro: risk_score=0, pháp vực=unknown;
  // nguy hiểm thật nằm ở hành lang.)
  const dangerCorridors = useMemo(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return [];
    const byCorridor = new Map<string, { name: string; risk: number; alerts: number; typ: string | null }>();
    for (const f of flows) {
      const key = `${f.source_name}→${f.target_name}`;
      const cur =
        byCorridor.get(key) ?? { name: `${f.source_name} → ${f.target_name}`, risk: 0, alerts: 0, typ: f.typology_hint };
      cur.risk = Math.max(cur.risk, f.risk_score);
      cur.alerts += f.alert_count;
      if (f.typology_hint) cur.typ = f.typology_hint;
      byCorridor.set(key, cur);
    }
    return [...byCorridor.values()].sort((a, b) => b.risk - a.risk || b.alerts - a.alerts).slice(0, 6);
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
        <span className="font-semibold text-ink-hi">Bộ dữ liệu: {datasetLabel(dataset)}</span>
      }
    >
      {dashboard.error && (
        <div className="rounded-panel border border-risk/40 bg-risk/10 px-4 py-2.5 text-data text-risk-soft" role="alert">
          {dashboard.error}
        </div>
      )}

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(168px,1fr))" }}>
        {dashboard.loading && !d ? (
          <CardSkeleton count={4} height={84} />
        ) : (
          kpis.map((kpi) => (
            <MetricCard
              key={kpi.label}
              label={kpi.label}
              value={kpi.value}
              tone={kpi.tone}
              note={kpi.note}
              onClick={kpi.onClick}
            />
          ))
        )}
      </div>

      <div className="flex flex-col gap-3.5">
        {/* Hàng trên: 3 thẻ ngang cân đối — rủi ro vụ việc · tuổi/phễu · hành lang rủi ro */}
        <div className="grid items-start gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
          <ChartCard
            title="Phân bố rủi ro vụ việc"
            subtitle={`${d?.cases_total ?? 0} vụ đang mở, theo dải điểm rủi ro`}
            spec={riskBandSpec}
            height={Math.max(110, (d?.case_risk_bands?.length ?? 3) * 44)}
            state={dashboard.loading ? "loading" : riskBandSpec ? "ok" : "empty"}
            note="Đếm thật từ vụ việc đang mở của đúng bộ dữ liệu này. Điểm rủi ro do bộ phát hiện chấm, cần người rà soát — không phải xác suất rửa tiền."
          />
            {/* Phễu xử lý: Cảnh báo → Vụ việc → Chờ duyệt SAR, kèm nút thắt
                phân công. Hữu ích cho cả chuyên viên (còn việc để nhận) lẫn quản
                lý (pipeline + tồn đọng). (Hành lang địa lý gộp vào panel bên
                cạnh — không để đồ thị hành lang ở hai chỗ.) */}
            <ChartCard
              title="Phễu xử lý"
              subtitle="Cảnh báo → Vụ việc → Chờ duyệt SAR"
              spec={funnelSpec}
              state={dashboard.loading ? "loading" : funnelSpec ? "ok" : "empty"}
              note={
                d && d.cases_unassigned > 0
                  ? `${int(d.cases_unassigned)}/${int(d.cases_total)} vụ CHƯA phân công — có thể nhận thêm / cần giao việc.`
                  : "Toàn bộ vụ đã có người phụ trách."
              }
            />

            <Panel title="Hành lang rủi ro cao nhất" subtitle="Xếp theo điểm rủi ro — cái đáng lo trước">
              {world.loading && <div className="h-24 animate-pulse rounded-control bg-elev/60" aria-hidden />}
              {world.data?.geography_available && dangerCorridors.length > 0 && (
                <div className="flex flex-col gap-3">
                  {dangerCorridors.map((c) => {
                    const tone: Tone = c.risk >= 80 ? "risk" : c.risk >= 60 ? "warn" : c.risk >= 40 ? "info" : "ok";
                    return (
                      <div key={c.name} className="flex flex-col gap-1">
                        <div className="flex items-baseline justify-between gap-2 text-data">
                          <span className="truncate-1 text-ink-hi">{c.name}</span>
                          <span className="tabular flex-none font-mono font-semibold" style={{ color: toneColor(tone) }}>
                            {c.risk}
                          </span>
                        </div>
                        <ProgressBar value={c.risk} tone={tone} />
                        <span className="truncate-1 text-meta text-ink-low">
                          {(c.typ && TYPOLOGY_LABELS[c.typ]?.name) || c.typ || "chưa rõ nhóm"} · {int(c.alerts)} cảnh báo
                        </span>
                      </div>
                    );
                  })}
                  <Link
                    to="/world"
                    className="mt-0.5 text-center text-data text-info-soft transition-colors hover:text-info"
                  >
                    Mở Giám sát địa lý →
                  </Link>
                </div>
              )}
              {world.data?.geography_available && dangerCorridors.length === 0 && (
                <div className="text-data text-ink-low">Chưa có hành lang nào vượt ngưỡng rủi ro.</div>
              )}
              {world.data && !world.data.geography_available && (
                <div className="rounded-control border border-warn/25 bg-warn/10 p-3 text-data text-warn-soft">
                  Chưa có dữ liệu địa lý đã kiểm chứng cho bộ dữ liệu này.
                </div>
              )}
            </Panel>
          </div>

          <ChartCard
            title="Xu hướng cảnh báo theo tuần"
            subtitle="Số cảnh báo mỗi tuần trên cả cửa sổ dữ liệu — bắt spike, không phải 5 cảnh báo lẻ"
            spec={trendSpec}
            state={dashboard.loading ? "loading" : trendSpec ? "ok" : "empty"}
            tools={["data", "dl", "full"]}
          />

          <Panel
            title="Hàng đợi ưu tiên — cần xử lý trước"
            padded={false}
            actions={
              <Link
                to="/cases"
                className="text-data text-info-soft transition-colors hover:text-info"
              >
                Mở danh sách vụ việc →
              </Link>
            }
          >
            <DataTable
              columns={queueColumns}
              rows={d?.top_alerts ?? []}
              rowKey={(alert) => alert.alert_id}
              onRowClick={(alert) => navigate(alert.case_id ? `/cases/${alert.case_id}` : `/alerts/${alert.alert_id}`)}
              loading={dashboard.loading && !d}
              minWidth={760}
              dense
              emptyTitle="Hàng đợi trống"
              emptyDetail="Không có cảnh báo nào đang chờ xử lý."
            />
          </Panel>
      </div>
    </PageShell>
  );
}
