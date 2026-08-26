import { useMemo, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { int } from "../api/fcFormat";
import { alertStatusLabel, datasetLabel, detectorLabel, formatRelative, sourceBrand } from "../api/format";
import { useApi } from "../api/useApi";
import { useConsole } from "../context/ConsoleContext";
import { useApp } from "../context/AppContext";
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
  PulseDot,
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

// Nhãn + tông màu cho phân bố rủi ro vụ việc và tuổi hồ sơ (dùng chung ở các
// biểu đồ). Để ngoài component để không vào deps của useMemo.
const BAND_META: Record<string, { label: string; tone: Tone }> = {
  critical: { label: "Nghiêm trọng", tone: "risk" },
  high: { label: "Cao", tone: "warn" },
  medium: { label: "Vừa", tone: "info" },
  low: { label: "Thấp", tone: "ok" },
};
const AGE_META: Record<string, { label: string; tone: Tone }> = {
  lt1d: { label: "< 1 ngày", tone: "ok" },
  d1_7: { label: "1–7 ngày", tone: "info" },
  d7_30: { label: "7–30 ngày", tone: "warn" },
  gt30d: { label: "> 30 ngày", tone: "risk" },
};

export function DashboardPage() {
  const navigate = useNavigate();
  const { dataset } = useConsole();
  const { currentUser } = useApp();
  // Dashboard theo vai trò: chuyên viên cần biết vụ nào GIÀ để xử trước; quản lý
  // cần thấy PHỄU xử lý và nút thắt (chưa phân công). Admin xem như quản lý.
  const showFunnel = currentUser?.role !== "analyst";
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
        note: d.latest_source_name ? sourceBrand(d.latest_source_name) : "chưa có lô dữ liệu",
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
        note: `${triggeredPct}% giao dịch vượt ngưỡng · release đang xem`,
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

  // Tuổi hồ sơ đang mở (chuyên viên): vụ nào đang GIÀ đi để ưu tiên xử trước.
  const ageSpec = useMemo<ChartSpec | null>(() => {
    if (!d?.case_age_buckets?.length) return null;
    return {
      type: "hbars",
      items: d.case_age_buckets.map((b) => ({
        label: AGE_META[b.bucket]?.label ?? b.bucket,
        value: b.count,
        color: toneColor(AGE_META[b.bucket]?.tone ?? "info"),
      })),
    };
  }, [d]);

  const corridorSpec = useMemo<ChartSpec | null>(() => {
    const flows = world.data?.flows;
    if (!flows?.length) return null;
    // Vẽ SỐ CẢNH BÁO, không vẽ volume_usd.
    //
    // volume_usd luôn bằng 0 vì dự án cố ý không quy đổi giữa các loại tiền —
    // biểu đồ vì thế hiện sáu cột 0 bên cạnh sáu tên hành lang. Xếp hạng cũng
    // đổi sang số cảnh báo: xếp theo risk_score đẩy lên đầu những hành lang chỉ
    // có ba bốn giao dịch, tỉ lệ 100% nhưng không nói lên điều gì.
    const top = [...flows].sort((a, b) => b.alert_count - a.alert_count).slice(0, 6);
    if (!top.some((flow) => flow.alert_count > 0)) return null;
    return {
      type: "hbars",
      items: top.map((flow) => ({
        label: `${flow.source_name} → ${flow.target_name}`,
        value: flow.alert_count,
        color: toneColor(flow.risk_score >= 80 ? "risk" : flow.risk_score >= 60 ? "warn" : "ok"),
        sub: `${flow.channel} · ${int(flow.txn_count)} giao dịch · rủi ro ${flow.risk_score}`,
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
          <span className="font-semibold text-ink-hi">Bộ dữ liệu: {datasetLabel(dataset)}</span> · lô{" "}
          {d?.latest_source_name ? sourceBrand(d.latest_source_name) : "chưa có nguồn"} · toàn bộ số liệu dưới đây là tổng của một lượt chạy trên
          đúng bộ này, không phải chuỗi thời gian
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

      <div className="flex flex-wrap items-start gap-3.5">
        <div className="flex min-w-0 flex-[2.4_1_520px] flex-col gap-3.5">
          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            <ChartCard
              title="Phân bố rủi ro vụ việc"
              subtitle={`${d?.cases_total ?? 0} vụ đang mở, theo dải điểm rủi ro`}
              spec={riskBandSpec}
              state={dashboard.loading ? "loading" : riskBandSpec ? "ok" : "empty"}
              note="Đếm thật từ vụ việc đang mở của đúng bộ dữ liệu này. Điểm rủi ro do bộ phát hiện chấm, cần người rà soát — không phải xác suất rửa tiền."
            />
            <ChartCard
              title="Hành lang địa lý"
              subtitle="Chỉ hiển thị khi nguồn có quốc gia/toạ độ đã kiểm chứng"
              spec={corridorSpec}
              tools={["data", "dl", "full"]}
              state={world.loading ? "loading" : corridorSpec ? "ok" : "empty"}
            />
          </div>

          {/* Biểu đồ THỨ HAI đổi theo vai trò: quản lý xem phễu xử lý + nút thắt
              phân công; chuyên viên xem tuổi hồ sơ để biết vụ nào cần xử trước. */}
          <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
            {showFunnel ? (
              <ChartCard
                title="Phễu xử lý"
                subtitle="Cảnh báo → Vụ việc → Chờ duyệt SAR"
                spec={funnelSpec}
                state={dashboard.loading ? "loading" : funnelSpec ? "ok" : "empty"}
                note={
                  d && d.cases_unassigned > 0
                    ? `${int(d.cases_unassigned)}/${int(d.cases_total)} vụ CHƯA phân công — nút thắt cần giao việc.`
                    : "Toàn bộ vụ đã có người phụ trách."
                }
              />
            ) : (
              <ChartCard
                title="Tuổi hồ sơ đang mở"
                subtitle="Vụ nào đang già đi — ưu tiên xử trước"
                spec={ageSpec}
                state={dashboard.loading ? "loading" : ageSpec ? "ok" : "empty"}
                note={
                  d && d.cases_unassigned > 0
                    ? `${int(d.cases_unassigned)} vụ chưa có người nhận — có thể nhận thêm.`
                    : undefined
                }
              />
            )}
          </div>

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
                        {/* Lượt chạm quốc gia, không phải số giao dịch: một giao dịch
                            nội địa tính cả chiều đi lẫn chiều đến, nên tổng đúng bằng
                            gấp đôi số giao dịch của bộ dữ liệu. */}
                        {int(hub.inbound + hub.outbound)} lượt
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
              ML đang phục vụ nguồn {d?.latest_source_name ? sourceBrand(d.latest_source_name) : "chưa xác định"}. Bản đồ dùng bảng tham chiếu
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
