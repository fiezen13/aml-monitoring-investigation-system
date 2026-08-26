import { AlertTriangle, BellPlus, BrainCircuit, Gauge } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { api, num } from "../api/client";
import { alertStatusLabel, detectorLabel, formatRelative, initials, profileValueLabel, datasetLabel } from "../api/format";
import { useApi } from "../api/useApi";
import { useConsole } from "../context/ConsoleContext";
import {
  Badge,
  Column,
  DataTable,
  MetricCard,
  Panel,
  PageShell,
  ProgressBar,
  RiskIndicator,
  SearchInput,
  Select,
} from "../components/ui";
import { ALERT_STATUS_TONE, DETECTOR_TONE } from "../design/semantic";
import { getRiskLabel, getRiskTone, RISK_THRESHOLDS } from "../design/risk";
import { toneColor } from "../design/semantic";
import type { ApiAlert } from "../api/client";
import { Pagination } from "../components/common/Pagination";

/**
 * Trung tâm cảnh báo.
 *
 * Dải phân bổ rủi ro trước đây dùng ngưỡng 75/50 và ba mã hex Tailwind mặc định
 * (`#EF4444`, `#F59E0B`, `#22C55E`) không có trong bảng màu nào của hệ thống —
 * nên cùng một cảnh báo 78 điểm hiện màu đỏ ở đây và màu hổ phách ở Tổng quan.
 * Giờ cả ngưỡng lẫn màu đều đến từ `design/risk`.
 */

const RISK_BANDS = [
  {
    key: "critical",
    name: `Nghiêm trọng (≥${RISK_THRESHOLDS.critical})`,
    test: (score: number) => score >= RISK_THRESHOLDS.critical,
  },
  {
    key: "high",
    name: `Cao (${RISK_THRESHOLDS.high}–${RISK_THRESHOLDS.critical - 1})`,
    test: (score: number) => score >= RISK_THRESHOLDS.high && score < RISK_THRESHOLDS.critical,
  },
  {
    key: "medium",
    name: `Trung bình (${RISK_THRESHOLDS.medium}–${RISK_THRESHOLDS.high - 1})`,
    test: (score: number) => score >= RISK_THRESHOLDS.medium && score < RISK_THRESHOLDS.high,
  },
  {
    key: "low",
    name: `Thấp (<${RISK_THRESHOLDS.medium})`,
    test: (score: number) => score < RISK_THRESHOLDS.medium,
  },
];

export function AlertsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [queryText, setQueryText] = useState("");
  const [typology, setTypology] = useState("");
  // Bộ dữ liệu lấy từ bộ chọn TOÀN CỤC ở header, không còn selector riêng của
  // trang này. Hàng đợi phục vụ nhiều bộ dữ liệu là hai vũ trụ tài khoản không
  // liên quan gì nhau; giờ mọi trang cùng đọc một lựa chọn nên không lệch nhau.
  const { dataset } = useConsole();
  const [page, setPage] = useState(1);
  const pageSize = 50;

  useEffect(() => {
    const timer = window.setTimeout(() => setQueryText(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => setPage(1), [typology, queryText, dataset]);

  const alerts = useApi(
    () =>
      api.alertsPage({
        typology_code: typology || undefined,
        q: queryText || undefined,
        dataset: dataset || undefined,
        page,
        page_size: pageSize,
      }),
    [typology, queryText, dataset, page],
    `alerts:${dataset}:${typology}:${queryText}:${page}`,
  );
  // Thẻ số liệu phải theo cùng bộ lọc với bảng, nếu không màn hình tự mâu thuẫn:
  // bảng hiện 5.004 dòng SAML-D còn thẻ ghi 10.004 cảnh báo.
  const dashboard = useApi(
    () => api.dashboard({ dataset: dataset || undefined }),
    [dataset],
    `dashboard:${dataset}`,
  );

  const rows = alerts.data?.rows ?? [];
  const total = alerts.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const riskDistribution = useMemo(
    () =>
      RISK_BANDS.map((band) => {
        // Lấy màu qua một điểm đại diện của dải, để dải và ô điểm trong bảng
        // không thể lệch nhau: cả hai đều đi qua `getRiskTone`.
        const sample = band.key === "critical" ? 90 : band.key === "high" ? 70 : band.key === "medium" ? 50 : 10;
        return {
          ...band,
          color: toneColor(getRiskTone(sample)),
          value: rows.filter((alert) => band.test(num(alert.risk_score))).length,
        };
      }).filter((band) => band.value > 0),
    [rows],
  );

  const columns: Column<ApiAlert>[] = [
    {
      key: "alert_id",
      header: "Mã cảnh báo",
      sortValue: (alert) => alert.alert_id,
      // Mã cảnh báo là một chuỗi băm dài; để nó tự xuống dòng thì mỗi hàng cao
      // gấp đôi và cột không còn quét dọc được bằng mắt.
      render: (alert) => (
        <span className="tabular whitespace-nowrap font-mono text-info-soft">{alert.alert_id}</span>
      ),
    },
    {
      key: "subject",
      header: "Chủ thể",
      render: (alert) => (
        <span className="inline-flex items-center gap-2">
          <span className="grid h-6 w-6 flex-none place-items-center rounded-full bg-elev text-meta font-semibold text-ink-soft">
            {initials(alert.customer_id)}
          </span>
          <span className="min-w-0">
            <span className="tabular block truncate font-mono text-data text-ink-hi">{alert.customer_id}</span>
            <span className="block truncate text-meta text-ink-low">{profileValueLabel(alert.occupation)}</span>
          </span>
        </span>
      ),
    },
    {
      key: "account",
      header: "Tài khoản",
      render: (alert) => (
        <div className="flex items-baseline gap-2">
          <span className="tabular font-mono text-ink-mid">{alert.account_key}</span>
          <span className="text-micro text-ink-low" title={`Bộ dữ liệu: ${alert.dataset}`}>
            {datasetLabel(alert.dataset)}
          </span>
        </div>
      ),
    },
    {
      key: "risk",
      header: "Điểm rủi ro",
      sortValue: (alert) => num(alert.risk_score),
      render: (alert) => <RiskIndicator score={num(alert.risk_score)} variant="badge" />,
    },
    {
      key: "detector",
      header: "Bộ phát hiện",
      render: (alert) => (
        <Badge tone={DETECTOR_TONE[alert.detector] ?? "neutral"}>{detectorLabel(alert.detector)}</Badge>
      ),
    },
    {
      key: "typology",
      header: "Nhóm hành vi",
      render: (alert) => (
        <span
          className="truncate-1 block max-w-[200px] text-ink-mid"
          title={`${alert.typology_label}. Gợi ý của hệ thống, cần con người rà soát.`}
        >
          {alert.typology_label}
        </span>
      ),
    },
    {
      key: "factors",
      header: "Yếu tố",
      numeric: true,
      sortValue: (alert) => alert.factor_count,
      render: (alert) => (
        <span title="Mỗi điểm rủi ro kèm tối thiểu ba yếu tố đóng góp">{alert.factor_count}</span>
      ),
    },
    {
      key: "status",
      header: "Trạng thái",
      render: (alert) => (
        <Badge tone={ALERT_STATUS_TONE[alert.status] ?? "neutral"}>{alertStatusLabel(alert.status)}</Badge>
      ),
    },
    {
      key: "created",
      header: "Phát sinh",
      sortValue: (alert) => alert.created_at,
      render: (alert) => <span className="text-ink-mid">{formatRelative(alert.created_at)}</span>,
    },
  ];

  const d = dashboard.data;

  return (
    <PageShell>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard
          label="Cảnh báo chưa đóng"
          value={d ? d.open_alerts : "—"}
          icon={<BellPlus size={14} aria-hidden />}
          note="Số cảnh báo chưa xử lý"
        />
        <MetricCard
          label={`Rủi ro cao (≥${RISK_THRESHOLDS.critical})`}
          value={d ? d.high_risk_alerts : "—"}
          tone="risk"
          icon={<AlertTriangle size={14} aria-hidden />}
          note={`Ngưỡng điểm ${RISK_THRESHOLDS.critical}/100`}
        />
        <MetricCard
          label="Điểm rủi ro trung bình"
          value={d ? d.avg_risk_score.toFixed(1) : "—"}
          icon={<Gauge size={14} aria-hidden />}
          note="Trung bình toàn bộ cảnh báo"
        />
        <MetricCard
          label="Vụ việc đang điều tra"
          value={d ? d.cases_investigating : "—"}
          tone="agent"
          icon={<BrainCircuit size={14} aria-hidden />}
          note="Chưa xuất hồ sơ, chưa đóng"
        />
      </div>

      <Panel
        padded={false}
        title="Hàng đợi cảnh báo"
        actions={
          <>
            <SearchInput
              value={search}
              onChange={setSearch}
              placeholder="Tìm mã cảnh báo, chủ thể, tài khoản…"
              className="w-64"
            />
            <Select
              aria-label="Lọc theo nhóm hành vi"
              value={typology}
              onChange={(event) => setTypology(event.target.value)}
              className="w-52"
            >
              <option value="">Tất cả nhóm hành vi</option>
              {(d?.typology_distribution ?? []).map((item) => (
                <option key={item.typology_code} value={item.typology_code}>
                  {item.typology_label}
                </option>
              ))}
            </Select>
          </>
        }
      >
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(alert) => alert.alert_id}
          // Hàng đợi chỉ để sàng: bấm một dòng mở thẳng VỤ VIỆC của nó (nơi
          // duy nhất xem chi tiết + điều tra AI). Cảnh báo mồ côi chưa gom vào
          // vụ thì mới rơi về trang cảnh báo tối giản.
          onRowClick={(alert) =>
            navigate(alert.case_id ? `/cases/${alert.case_id}` : `/alerts/${alert.alert_id}`)
          }
          loading={alerts.loading}
          error={alerts.error}
          onRetry={alerts.reload}
          minWidth={980}
          emptyDetail={
            queryText ? `Không có cảnh báo nào khớp “${queryText}”.` : "Chưa có cảnh báo nào trong hệ thống."
          }
          footer={
            <Pagination
              page={page}
              pageCount={pageCount}
              onChange={setPage}
              summary={
                total
                  ? `Cảnh báo ${(page - 1) * pageSize + 1}–${Math.min(page * pageSize, total)} trong tổng số ${total}`
                  : "Không có cảnh báo"
              }
            />
          }
        />
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Phân bổ rủi ro của trang hiện tại" subtitle={`Tối đa ${pageSize} cảnh báo · ngưỡng ${RISK_THRESHOLDS.critical}/${RISK_THRESHOLDS.high}/${RISK_THRESHOLDS.medium}`}>
          {riskDistribution.length === 0 ? (
            <p className="text-meta text-ink-low">Không có cảnh báo nào để phân bổ.</p>
          ) : (
            <div className="flex items-center gap-4">
              <div className="relative h-32 w-32 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={riskDistribution}
                      dataKey="value"
                      innerRadius={42}
                      outerRadius={58}
                      strokeWidth={0}
                      isAnimationActive={false}
                    >
                      {riskDistribution.map((band) => (
                        <Cell key={band.key} fill={band.color} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="tabular font-mono text-h3 font-bold text-ink-hi">{rows.length}</span>
                  <span className="text-micro uppercase tracking-wide text-ink-low">Tổng</span>
                </div>
              </div>
              <ul className="flex-1 space-y-2 text-meta">
                {riskDistribution.map((band) => (
                  <li key={band.key} className="flex items-center gap-2">
                    <span className="h-2 w-2 flex-none rounded-full" style={{ background: band.color }} aria-hidden />
                    <span className="flex-1 text-ink-mid">{band.name}</span>
                    <span className="tabular font-mono font-semibold text-ink-hi">
                      {band.value} ({Math.round((band.value / (rows.length || 1)) * 100)}%)
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>

        <Panel title="Phân bổ theo nhóm hành vi">
          {!d ? (
            <div className="h-24 animate-pulse rounded-control bg-elev/60" aria-hidden />
          ) : (
            <div className="space-y-3">
              {d.typology_distribution.map((typologyRow) => (
                <div key={typologyRow.typology_code}>
                  <div className="mb-1 flex items-center justify-between gap-3 text-meta">
                    <span className="min-w-0 truncate text-ink-mid">
                      <span className="tabular font-mono font-semibold text-ink-hi">{typologyRow.typology_code}</span>{" "}
                      {typologyRow.typology_label}
                    </span>
                    <span className="tabular flex-none font-mono font-semibold text-ink-hi">
                      {typologyRow.alert_count} ({typologyRow.share_pct}%)
                    </span>
                  </div>
                  <ProgressBar value={typologyRow.share_pct} tone="primary" />
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <p className="text-meta leading-relaxed text-ink-low">
        Chủ thể được định danh bằng mã khách hàng và mô tả nghề nghiệp — lược đồ cố ý không lưu họ tên vì đây là dữ
        liệu tổng hợp, không phải khách hàng thật. Nhãn dải rủi ro (“{getRiskLabel(85)}”, “{getRiskLabel(65)}”…) dùng
        đúng một thang với ô điểm trong bảng.
      </p>
    </PageShell>
  );
}
