import { useMemo, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, num } from "../api/client";
import { int } from "../api/fcFormat";
import { alertStatusLabel, caseStateLabel, datasetLabel, formatRelative } from "../api/format";
import { TYPOLOGY_LABELS } from "../api/typologyLabels";
import { useApi } from "../api/useApi";
import { useApp } from "../context/AppContext";
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
  SectionHeader,
} from "../components/ui";
import { ALERT_STATUS_TONE, type Tone } from "../design/semantic";
import { toneColor } from "../design";
import type { ApiAlert, ApiWorkload, ApiWorkloadRow } from "../api/client";

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

/** "Tiếp nhận cảnh báo 2 · Điều tra bổ sung 1" — vụ của tôi đang nằm ở bước nào. */
function stateBreakdown(byState: Record<string, number> | undefined): string {
  const parts = Object.entries(byState ?? {}).sort((a, b) => b[1] - a[1]);
  if (parts.length === 0) return "Chưa có vụ nào đang giữ";
  return parts.map(([state, n]) => `${caseStateLabel(state)} ${n}`).join(" · ");
}

export function DashboardPage() {
  const navigate = useNavigate();
  const { dataset } = useConsole();
  // `dataset` nằm trong deps: đổi bộ dữ liệu ở header thì Tổng quan hỏi lại
  // ngay, không còn cảnh thẻ số một bộ mà biểu đồ lại bộ khác.
  const dashboard = useApi(() => api.dashboard({ dataset }), [dataset], `dashboard:${dataset}`);
  const world = useApi(() => api.world({ dataset }), [dataset], `world:${dataset}`);
  const hasGeography = Boolean(world.data?.geography_available);
  // Đã có sẵn trong payload /dashboard và lọc đúng bộ dữ liệu, nhưng trước
  // nay không trang nào vẽ ra.
  const typologyShares = dashboard.data?.typology_distribution ?? [];

  const d = dashboard.data;
  const casesAwaitingReview = d?.cases_awaiting_review ?? d?.cases_total ?? 0;

  // Chuyên viên làm việc trên một phạm vi duy nhất: bộ dữ liệu đang chọn. Không
  // trộn số của một bản phát hành riêng với tổng tồn đọng của các cách phát hiện.
  const overviewKpis = useMemo<
    { label: string; value: ReactNode; tone: Tone; note: ReactNode; onClick?: () => void }[]
  >(() => {
    if (!d) return [];
    return [
      {
        label: "Giao dịch đã phân tích",
        value: d.transactions_analyzed,
        tone: "neutral",
        note: `toàn bộ giao dịch của ${datasetLabel(dataset)}`,
      },
      {
        label: "Cảnh báo cần rà soát",
        value: d.open_alerts,
        tone: "risk",
        note: "tổng số cảnh báo chưa đóng",
      },
      {
        label: "Vụ việc đang mở",
        value: d.cases_total,
        tone: "agent",
        note: "mỗi cảnh báo đã có một hồ sơ · mở danh sách →",
        onClick: () => navigate("/cases"),
      },
      {
        label: "Chờ chuyên viên rà soát",
        value: casesAwaitingReview,
        tone: "warn",
        note: "đã có hồ sơ, chưa gọi AI",
      },
    ];
  }, [casesAwaitingReview, d, dataset, navigate]);

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

  // Tình trạng xử lý dùng TOÀN BỘ vụ việc của bộ dữ liệu. Các dòng là trạng
  // thái vận hành có thể giao nhau, không phải phép trừ của một phễu.
  const funnelSpec = useMemo<ChartSpec | null>(() => {
    if (!d) return null;
    const c = d.cases_total;
    const waiting = casesAwaitingReview;
    const assigned = Math.max(0, c - d.cases_unassigned);
    const s = d.sar_pending;
    if (c + waiting + assigned + s === 0) return null;
    return {
      type: "hbars",
      items: [
        { label: "Vụ việc đang mở", value: c, color: toneColor("agent") },
        { label: "Chờ chuyên viên rà soát", value: waiting, color: toneColor("warn") },
        { label: "Đã giao chuyên viên", value: assigned, color: toneColor("info") },
        { label: "Chờ duyệt SAR", value: s, color: toneColor("risk") },
      ],
    };
  }, [casesAwaitingReview, d]);

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

  // Số liệu công việc phải khớp THẨM QUYỀN của vai trò. Bảng "ai đang gánh bao
  // nhiêu" là công cụ chia việc của Quản lý; Chuyên viên không phân công cho ai
  // nên nó vừa vô dụng vừa để lộ khối lượng việc của đồng nghiệp. API cũng đã
  // khoá "/workload" lại cho Quản lý, nên Chuyên viên gọi vào sẽ nhận 403 —
  // đừng gọi.
  const { currentUser } = useApp();
  const isManager = currentUser?.role === "manager";
  const myWork = useApi(() => api.myWork(), []);
  const workload = useApi<ApiWorkload | null>(
    () => (isManager ? api.workload() : Promise.resolve(null)),
    [isManager],
  );
  const workloadColumns: Column<ApiWorkloadRow>[] = [
    {
      key: "name",
      header: "Người xử lý",
      render: (r) => (
        <div className="flex flex-col">
          <span className="font-medium text-ink-hi">{r.name}</span>
          <span className="text-meta text-ink-low">{r.role_label}</span>
        </div>
      ),
    },
    {
      key: "open",
      header: "Vụ đang giữ",
      numeric: true,
      render: (r) => <span className="tabular font-mono font-semibold text-ink-hi">{int(r.open_cases)}</span>,
    },
    {
      key: "states",
      header: "Đang ở bước",
      render: (r) => {
        const parts = Object.entries(r.by_state).sort((a, b) => b[1] - a[1]);
        if (parts.length === 0) return <span className="text-ink-low">—</span>;
        return (
          <span className="truncate-1 text-ink-mid" title={parts.map(([k, n]) => `${caseStateLabel(k)}: ${n}`).join(" · ")}>
            {parts.map(([k, n]) => `${caseStateLabel(k)} ${n}`).join(" · ")}
          </span>
        );
      },
    },
    {
      key: "sar",
      header: "Hồ sơ đã nộp / được duyệt",
      numeric: true,
      render: (r) => (
        <span className="tabular font-mono text-ink-mid">
          {int(r.sar_submitted)} / <span className="text-ink-hi">{int(r.sar_approved)}</span>
        </span>
      ),
    },
    {
      key: "closed",
      header: "Vụ đã kết thúc",
      numeric: true,
      render: (r) => <span className="tabular font-mono text-ink-mid">{int(r.closed_cases)}</span>,
    },
  ];

  const queueColumns: Column<ApiAlert>[] = [
    {
      key: "alert_id",
      header: "Vụ việc",
      render: (alert) => (
        <span className="tabular whitespace-nowrap font-mono text-data text-primary">
          {alert.case_id ?? alert.alert_id}
        </span>
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

      <section aria-labelledby="overview-summary-title">
        <SectionHeader
          title={<span id="overview-summary-title">Tổng quan bộ dữ liệu {datasetLabel(dataset)}</span>}
          className="max-lg:flex-col max-lg:items-start"
          actions={
            d ? (
              <span className="tabular text-right text-meta text-ink-low max-lg:text-left">
                {int(d.transactions_analyzed)} giao dịch → {int(d.open_alerts)} cảnh báo → {int(d.cases_total)} vụ việc
              </span>
            ) : undefined
          }
        />
        <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(168px,1fr))" }}>
          {dashboard.loading && !d ? (
            <CardSkeleton count={4} height={84} />
          ) : (
            overviewKpis.map((kpi) => (
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
      </section>

      <div className="flex flex-col gap-3.5">
        {/* Hàng trên: 3 thẻ ngang cân đối — rủi ro vụ việc · tuổi/phễu · hành lang rủi ro */}
        <div className="grid items-start gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(300px,1fr))" }}>
          <ChartCard
            title="Phân bố rủi ro vụ việc"
            subtitle={`${d?.cases_total ?? 0} vụ đang mở, theo dải điểm rủi ro`}
            spec={riskBandSpec}
            height={Math.max(110, (d?.case_risk_bands?.length ?? 3) * 44)}
            state={dashboard.loading ? "loading" : riskBandSpec ? "ok" : "empty"}
            note="Đếm thật từ vụ việc đang mở của đúng bộ dữ liệu này. Điểm rủi ro dùng để xếp thứ tự ưu tiên, không phải kết luận rửa tiền."
          />
            {/* Tình trạng xử lý dùng toàn bộ vụ việc của bộ dữ liệu đang chọn. */}
            <ChartCard
              title="Tình trạng vụ việc"
              subtitle="Toàn bộ hồ sơ đang mở của bộ dữ liệu đang chọn"
              spec={funnelSpec}
              state={dashboard.loading ? "loading" : funnelSpec ? "ok" : "empty"}
              note={
                d
                  ? `${int(casesAwaitingReview)} vụ đã sẵn sàng để chuyên viên rà soát trước khi quyết định gọi AI.`
                  : undefined
              }
            />

            {/* Bộ dữ liệu KHÔNG có địa lý thì đổi hẳn nội dung ô, không để một ô
                trống mang tiêu đề "Hành lang rủi ro".
                Bộ IBM không mang quốc gia trên giao dịch nên không có hành lang
                nào để xếp hạng — nhưng nó có NHÓM HÀNH VI, và "nhóm nào đang
                nhiều nhất" mới là câu hỏi chuyên viên cần trả lời ở đây. */}
            <Panel
              title={hasGeography ? "Hành lang rủi ro cao nhất" : "Nhóm hành vi đang nhiều nhất"}
              subtitle={
                hasGeography
                  ? "Xếp theo điểm rủi ro — cái đáng lo trước"
                  : "Cảnh báo chưa đóng của bộ dữ liệu đang xem, xếp theo số lượng"
              }
            >
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
              {!hasGeography && typologyShares.length > 0 && (
                <div className="flex flex-col gap-3">
                  {typologyShares.map((t) => (
                    <div key={t.typology_code} className="flex flex-col gap-1">
                      <div className="flex items-baseline justify-between gap-2 text-data">
                        <span className="truncate-1 text-ink-hi" title={t.typology_label}>
                          {t.typology_label}
                        </span>
                        <span className="tabular flex-none font-mono font-semibold text-ink-hi">
                          {int(t.alert_count)}
                        </span>
                      </div>
                      <ProgressBar value={t.share_pct} tone="info" />
                      <span className="text-meta text-ink-low">{t.share_pct}% tổng cảnh báo chưa đóng</span>
                    </div>
                  ))}
                  <Link
                    to="/cases"
                    className="mt-0.5 text-center text-data text-info-soft transition-colors hover:text-info"
                  >
                    Mở danh sách vụ việc →
                  </Link>
                </div>
              )}
              {!hasGeography && !dashboard.loading && typologyShares.length === 0 && (
                <div className="text-data text-ink-low">Chưa có cảnh báo nào đang mở cho bộ dữ liệu này.</div>
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

          {/* Số liệu công việc, TÁCH THEO VAI TRÒ.

              Chuyên viên hỏi "việc của tôi đang ở đâu": vụ được giao, hồ sơ đã
              trình, hồ sơ bị trả lại. Quản lý hỏi "đội đang gánh gì và tôi phải
              duyệt bao nhiêu". Trước đây cả hai vai cùng thấy một bảng nhân sự,
              tức Chuyên viên vừa xem được khối lượng việc của đồng nghiệp vừa
              không tìm được con số của chính mình. */}
          {isManager ? (
            <Panel
              title="Phân công và khối lượng công việc"
              subtitle={
                workload.data
                  ? `${int(workload.data.unassigned_cases)} vụ chưa ai giữ trên tổng ${int(workload.data.total_open_cases)} vụ đang mở`
                  : "Đang tải…"
              }
              padded={false}
              actions={
                <Link to="/cases?assignment=unassigned" className="text-data text-info-soft transition-colors hover:text-info">
                  Mở hàng đợi chưa giao →
                </Link>
              }
            >
              <div className="grid gap-3 p-4 sm:grid-cols-3">
                <MetricCard
                  label="Hồ sơ chờ tôi phê duyệt"
                  value={myWork.data?.awaiting_my_decision ?? 0}
                  tone={(myWork.data?.awaiting_my_decision ?? 0) > 0 ? "warn" : "neutral"}
                  // Hồ sơ do CHÍNH mình trình đã bị trừ khỏi con số trên — bốn
                  // mắt chặn ở cổng quyết định. Nhưng nó vẫn đang treo, nên phải
                  // nói ra, không thì vụ kẹt im lặng và không ai biết vì sao.
                  note={
                    (myWork.data?.submitted_pending ?? 0) > 0
                      ? `${int(myWork.data?.submitted_pending ?? 0)} hồ sơ do chính tôi trình phải để Quản lý khác duyệt`
                      : "Chuyên viên đã trình, đang chờ quyết định"
                  }
                  size="sm"
                  onClick={() => navigate("/approvals")}
                />
                <MetricCard
                  label="Vụ chưa giao cho ai"
                  value={myWork.data?.unassigned_cases ?? 0}
                  note="Cần chia việc"
                  size="sm"
                  onClick={() => navigate("/cases?assignment=unassigned")}
                />
                <MetricCard
                  label="Vụ chuyên viên đang xử lý"
                  value={(workload.data?.total_open_cases ?? 0) - (myWork.data?.unassigned_cases ?? 0)}
                  note="Đã có người phụ trách"
                  size="sm"
                  onClick={() => navigate("/cases")}
                />
              </div>
              <DataTable
                columns={workloadColumns}
                rows={(workload.data?.rows ?? []).filter((r) => r.active)}
                rowKey={(r) => r.user_id}
                loading={workload.loading && !workload.data}
                minWidth={640}
                dense
                emptyTitle="Chưa có người xử lý"
                emptyDetail="Chưa có tài khoản Chuyên viên hoặc Quản lý nào đang hoạt động."
              />
            </Panel>
          ) : (
            <Panel
              title="Việc của tôi"
              subtitle={
                myWork.data
                  ? `${int(myWork.data.assigned_open)} vụ đang giữ · ${int(myWork.data.submitted_pending)} hồ sơ đang chờ quản lý duyệt`
                  : "Đang tải…"
              }
              actions={
                <Link to="/cases?assignment=mine" className="text-data text-info-soft transition-colors hover:text-info">
                  Mở vụ việc của tôi →
                </Link>
              }
            >
              {myWork.loading && !myWork.data ? (
                <CardSkeleton />
              ) : (
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  <MetricCard
                    label="Vụ được giao cho tôi"
                    value={myWork.data?.assigned_open ?? 0}
                    note={stateBreakdown(myWork.data?.assigned_by_state)}
                    size="sm"
                    onClick={() => navigate("/cases?assignment=mine")}
                  />
                  <MetricCard
                    label="Đã trình, chờ quản lý duyệt"
                    value={myWork.data?.submitted_pending ?? 0}
                    tone={(myWork.data?.submitted_pending ?? 0) > 0 ? "info" : "neutral"}
                    note="Không còn việc của tôi cho tới khi có quyết định"
                    size="sm"
                  />
                  <MetricCard
                    label="Bị trả lại cần bổ sung"
                    value={myWork.data?.returned_for_info ?? 0}
                    tone={(myWork.data?.returned_for_info ?? 0) > 0 ? "warn" : "neutral"}
                    note="Quản lý yêu cầu làm rõ thêm"
                    size="sm"
                  />
                  <MetricCard
                    label="Hồ sơ đã được duyệt"
                    value={myWork.data?.submitted_approved ?? 0}
                    tone="ok"
                    note={`${int(myWork.data?.closed_cases ?? 0)} vụ tôi xử lý đã kết thúc`}
                    size="sm"
                  />
                </div>
              )}
            </Panel>
          )}

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
