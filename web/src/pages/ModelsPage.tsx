import { useMemo } from "react";

import { api } from "../api/client";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { Chip, Empty, KpiCard, Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * Model Monitoring — theo dõi mô hình sau khi triển khai.
 *
 * Trôi phân phối (PSI) là chỉ số cần nhìn kỹ nhất: mô hình không hỏng đột
 * ngột, nó lệch dần khi hành vi thực tế đổi khác so với dữ liệu huấn luyện.
 * Đến lúc chỉ số phát hiện tụt xuống thì đã trễ vài tuần.
 */

const METRIC_LABEL: Record<string, string> = {
  alert_volume: "Số cảnh báo mỗi ngày",
  psi_amount: "PSI — trôi phân phối số tiền",
  avg_risk_score: "Điểm rủi ro trung bình",
  p95_latency_ms: "Độ trễ p95 (ms)",
};

const STATUS_COLOR: Record<string, string> = { ok: C.ok, watch: C.warn, breach: C.risk };
const STATUS_LABEL: Record<string, string> = { ok: "Bình thường", watch: "Cần theo dõi", breach: "Vượt ngưỡng" };

/** Ngưỡng cảnh báo PSI theo thông lệ: 0.10 bắt đầu chú ý, 0.25 là phải hành động. */
const PSI_WATCH = 0.2;
const PSI_BREACH = 0.25;

export function ModelsPage() {
  const data = useApi(() => api.modelMonitor(), []);
  const rows = data.data ?? [];

  // Gom theo chỉ số để vẽ chuỗi thời gian; mỗi chỉ số một biểu đồ vì đơn vị
  // khác nhau hoàn toàn (đếm, tỷ lệ, mili giây).
  const byMetric = useMemo(() => {
    const map = new Map<string, typeof rows>();
    for (const r of rows) {
      const list = map.get(r.metric_name) ?? [];
      list.push(r);
      map.set(r.metric_name, list);
    }
    for (const list of map.values()) {
      list.sort((a, b) => new Date(a.observed_at).getTime() - new Date(b.observed_at).getTime());
    }
    return map;
  }, [rows]);

  const latest = useMemo(() => {
    const out: { metric: string; value: number; status: string; at: string }[] = [];
    for (const [metric, list] of byMetric) {
      const last = list[list.length - 1];
      if (last) out.push({ metric, value: last.metric_value, status: last.status, at: last.observed_at });
    }
    return out;
  }, [byMetric]);

  const breaches = latest.filter((l) => l.status === "breach").length;
  const watching = latest.filter((l) => l.status === "watch").length;

  const specFor = (metric: string): ChartSpec | null => {
    const list = byMetric.get(metric);
    if (!list?.length) return null;
    const isPsi = metric === "psi_amount";
    return {
      type: "line",
      labels: list.map((r) => new Date(r.observed_at).toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })),
      series: [
        {
          name: METRIC_LABEL[metric] ?? metric,
          data: list.map((r) => r.metric_value),
          color: isPsi ? C.warn : C.primary,
        },
      ],
      // Vẽ ngưỡng ngay trên biểu đồ: nhìn một con số đơn lẻ không biết nó cao
      // hay thấp, nhìn nó so với đường ngưỡng thì biết ngay.
      refs: isPsi
        ? [
            { v: PSI_WATCH, label: "cần theo dõi 0.20", color: "rgba(245,165,36,0.6)" },
            { v: PSI_BREACH, label: "vượt ngưỡng 0.25", color: "rgba(255,77,97,0.6)" },
          ]
        : undefined,
    };
  };

  return (
    <div className="flex animate-up flex-col gap-3.5 p-4">
      <ScreenTitle
        title="Model Monitoring"
        meta={rows[0] ? `${rows[0].model_version} · 14 ngày gần nhất` : "Chưa có dữ liệu giám sát"}
      />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard
          label="Chỉ số vượt ngưỡng"
          value={breaches}
          valueColor={breaches ? C.risk : C.ok}
          delta={breaches ? "cần hành động" : "không có"}
        />
        <KpiCard label="Chỉ số cần theo dõi" value={watching} valueColor={watching ? C.warn : C.inkLow} delta="chớm lệch" />
        {latest.map((l) => (
          <KpiCard
            key={l.metric}
            label={METRIC_LABEL[l.metric] ?? l.metric}
            value={l.value < 1 ? l.value.toFixed(3) : Math.round(l.value)}
            valueColor={STATUS_COLOR[l.status] ?? C.inkHi}
            delta={STATUS_LABEL[l.status] ?? l.status}
          />
        ))}
      </div>

      {data.loading && <Skeleton rows={6} />}
      {!data.loading && !rows.length && (
        <Empty text="Chưa có dữ liệu giám sát mô hình" hint="Chạy scripts/abm_generate.py để sinh dữ liệu" />
      )}

      <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))" }}>
        {[...byMetric.keys()].map((metric) => (
          <ChartCard
            key={metric}
            title={METRIC_LABEL[metric] ?? metric}
            subtitle={metric === "psi_amount" ? "Chỉ số cần nhìn kỹ nhất — mô hình lệch dần chứ không hỏng đột ngột" : "14 ngày gần nhất"}
            spec={specFor(metric)}
            tools={["data", "dl", "full"]}
            state="ok"
            note={metric === "psi_amount" ? "PSI vượt 0.25 nghĩa là phân phối đầu vào đã khác đáng kể so với lúc huấn luyện." : undefined}
          />
        ))}
      </div>

      {latest.some((l) => l.status !== "ok") && (
        <Panel title="Việc cần làm" subtitle="Khi một chỉ số rời khỏi vùng bình thường">
          <ol className="flex list-decimal flex-col gap-2 pl-5 text-xs leading-relaxed text-ink-soft">
            <li>
              Xác định trôi đến từ đâu: dữ liệu nguồn đổi, hành vi thực tế đổi, hay chính đường ống nạp có lỗi. Xem
              màn hình Data Quality trước khi kết luận là mô hình có vấn đề.
            </li>
            <li>
              Kiểm tra chỉ số phát hiện ở màn hình Benchmarks. Trôi phân phối chưa chắc làm giảm chất lượng phát hiện —
              nhưng nếu cả hai cùng xấu đi thì nguyên nhân đã rõ.
            </li>
            <li>
              Không tự động huấn luyện lại theo lịch cố định. Huấn luyện lại trên dữ liệu đã trôi mà không hiểu nguyên
              nhân sẽ khoá lỗi vào trong mô hình.
            </li>
          </ol>
        </Panel>
      )}

      <Panel bodyClassName="overflow-x-auto px-0" title="Bản ghi gần nhất">
        <div className="min-w-[640px]">
          <div
            className="grid gap-2 border-b border-line px-3 py-2 text-3xs uppercase tracking-[0.07em] text-ink-low"
            style={{ gridTemplateColumns: "220px 130px 130px 120px 1fr" }}
          >
            <span>Chỉ số</span>
            <span className="text-right">Giá trị</span>
            <span className="text-right">Điểm trôi</span>
            <span>Trạng thái</span>
            <span>Thời điểm</span>
          </div>
          {[...rows]
            .sort((a, b) => new Date(b.observed_at).getTime() - new Date(a.observed_at).getTime())
            .slice(0, 20)
            .map((r, i) => (
              <div
                key={`${r.metric_name}-${r.observed_at}-${i}`}
                className="grid items-center gap-2 border-b border-line-faint px-3 py-[7px] text-base"
                style={{ gridTemplateColumns: "220px 130px 130px 120px 1fr" }}
              >
                <span className="truncate-1 text-xs">{METRIC_LABEL[r.metric_name] ?? r.metric_name}</span>
                <span className="tabular text-right font-mono text-xs">
                  {r.metric_value < 1 ? r.metric_value.toFixed(4) : r.metric_value.toFixed(1)}
                </span>
                <span className="tabular text-right font-mono text-xs text-ink-soft">
                  {r.drift_score != null ? r.drift_score.toFixed(4) : "—"}
                </span>
                <Chip color={STATUS_COLOR[r.status] ?? C.inkSoft}>{STATUS_LABEL[r.status] ?? r.status}</Chip>
                <span className="text-xs text-ink-low">{formatDateTime(r.observed_at)}</span>
              </div>
            ))}
        </div>
      </Panel>
    </div>
  );
}
