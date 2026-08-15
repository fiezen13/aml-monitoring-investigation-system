import { useMemo } from "react";

import { api } from "../api/client";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { ErrorState, PageShell } from "../components/ui";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { Chip, Empty, KpiCard, Panel, ProgressBar, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";

/**
 * Đánh giá chuẩn — kết quả kiểm định mức độ phát hiện.
 *
 * Không có độ chính xác tổng thể ở đây, và đó là chủ ý. Với tỷ lệ dương thật cỡ phần nghìn,
 * một mô hình trả lời "không có gì bất thường" cho mọi giao dịch vẫn đạt
 * độ chính xác tổng thể 99,9%. Các chỉ số dưới đây đo thứ có ý nghĩa vận hành: xếp đúng thứ
 * tự ưu tiên, phát hiện sớm được bao lâu, và gắn cờ nhầm bao nhiêu trên nhóm
 * hợp pháp trông giống đối tượng nghi vấn.
 */

const METRIC_LABEL: Record<string, string> = {
  precision_at_50: "Độ chính xác trong 50 cảnh báo đầu",
  recall_at_50: "Độ bao phủ trong 50 cảnh báo đầu",
  false_positive_rate_hard_negative: "Dương tính giả trên mẫu âm khó",
  detection_lead_time_days: "Thời gian phát hiện sớm (ngày)",
  alert_to_case_conversion: "Tỷ lệ cảnh báo thành vụ việc",
  evidence_coverage: "Độ phủ bằng chứng",
  f1_mean_5_seeds: "F1 trung bình 5 seed",
  f1_primary_seed: "F1 seed chính",
  f1_sample_std_5_seeds: "Độ lệch chuẩn F1 qua 5 seed",
  pr_auc_primary_seed: "PR-AUC seed chính",
  precision_primary_seed: "Precision seed chính",
  recall_primary_seed: "Recall seed chính",
};

const METRIC_HINT: Record<string, string> = {
  precision_at_50:
    "Trong 50 cảnh báo xếp đầu, bao nhiêu phần là đáng điều tra. Đây là chỉ số chuyên viên trực tiếp cảm nhận được.",
  recall_at_50: "Trong toàn bộ trường hợp đáng chú ý, bao nhiêu phần lọt vào 50 vị trí đầu.",
  false_positive_rate_hard_negative:
    "Tỷ lệ gắn cờ nhầm trên nhóm hợp pháp cố ý trông giống đối tượng nghi vấn. Thấp mới là tốt.",
  detection_lead_time_days:
    "Khoảng cách giữa lúc mô hình gắn cờ và lúc đủ bằng chứng xác nhận. Càng dài càng có thời gian can thiệp.",
  alert_to_case_conversion: "Bao nhiêu phần cảnh báo được nâng thành vụ việc thay vì đóng lại.",
  evidence_coverage: "Bao nhiêu phần khẳng định trong hồ sơ neo được vào một mục bằng chứng cụ thể.",
  f1_mean_5_seeds: "Trung bình điều hòa giữa precision và recall trên năm lần chạy với seed độc lập.",
  f1_primary_seed: "F1 trên seed phát hành chính, dùng cùng test split và threshold đã khóa.",
  f1_sample_std_5_seeds: "Độ dao động của F1 giữa năm seed; càng thấp mô hình càng ổn định.",
  pr_auc_primary_seed: "Diện tích dưới đường precision-recall, phù hợp với bài toán mất cân bằng lớp.",
  precision_primary_seed: "Tỷ lệ dương thật trong các giao dịch được model gắn cờ trên test split.",
  recall_primary_seed: "Tỷ lệ giao dịch dương thật được model tìm thấy trên test split.",
};

/** Với các chỉ số này, giá trị thấp mới là đạt. */
const LOWER_IS_BETTER = new Set(["false_positive_rate_hard_negative", "f1_sample_std_5_seeds"]);

export function BenchmarksPage() {
  const data = useApi(() => api.benchmarks(), []);
  const rows = data.data ?? [];

  const passed = rows.filter((r) => r.passed === true).length;
  const failed = rows.filter((r) => r.passed === false).length;

  const spec = useMemo<ChartSpec | null>(() => {
    const ratio = rows.filter((r) => r.metric_value <= 1 && r.target_value != null);
    if (!ratio.length) return null;
    return {
      type: "bars",
      labels: ratio.map((r) => (METRIC_LABEL[r.metric_name] ?? r.metric_name).slice(0, 22)),
      series: [
        { name: "Đạt được", data: ratio.map((r) => r.metric_value), color: C.primary },
        { name: "Ngưỡng yêu cầu", data: ratio.map((r) => r.target_value!), color: C.inkDim },
      ],
    };
  }, [rows]);

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Đánh giá chuẩn"
        meta="Kiểm định mức độ phát hiện — ngưỡng được đặt trước khi có kết quả, không chỉnh sau"
      />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard label="Chỉ số đạt" value={passed} valueColor={C.ok} delta={`trên ${rows.length} chỉ số`} />
        <KpiCard label="Chỉ số chưa đạt" value={failed} valueColor={failed ? C.risk : C.inkLow} delta="cần xem lại" />
        <KpiCard
          label="Gói kịch bản"
          value={<span className="text-2xl">{rows[0]?.scenario_package ?? "—"}</span>}
          delta="đang kiểm định"
        />
        <KpiCard
          label="Phiên bản mô hình"
          value={<span className="text-2xl">{rows[0]?.model_version ?? "—"}</span>}
          delta={rows[0] ? `tập ${rows[0].split}` : ""}
        />
      </div>

      <ChartCard
        title="Đạt được so với ngưỡng"
        subtitle="Chỉ các chỉ số theo thang 0–1; thời gian phát hiện sớm tính bằng ngày nên tách riêng bên dưới"
        height={186}
        spec={spec}
        tools={["data", "dl", "full"]}
        state={data.loading ? "loading" : spec ? "ok" : "empty"}
      />

      {data.loading && <Skeleton rows={5} />}
      {data.error && <ErrorState detail={data.error} onRetry={data.reload} />}
      {!data.loading && !data.error && !rows.length && (
        <Empty
          text="Release đang hoạt động chưa có kết quả kiểm định được công bố"
          hint="Chạy pipeline benchmark đã khóa split và threshold, sau đó xuất kết quả vào PostgreSQL."
        />
      )}

      <div className="flex flex-col gap-2.5">
        {rows.map((r) => {
          const lower = LOWER_IS_BETTER.has(r.metric_name);
          // Thanh tiến độ luôn theo hướng "dài hơn = tốt hơn", kể cả với chỉ số
          // mà giá trị thấp mới đạt — nếu không, cùng một hình ảnh sẽ mang hai
          // nghĩa trái ngược trên cùng một màn hình.
          const ratio = r.target_value
            ? lower
              ? Math.min(100, (r.target_value / Math.max(r.metric_value, 0.0001)) * 100)
              : Math.min(100, (r.metric_value / r.target_value) * 100)
            : null;
          const color = r.passed === false ? C.risk : r.passed === true ? C.ok : C.inkSoft;
          return (
            <Panel key={r.id} className="p-0">
              <div className="flex flex-wrap items-start gap-3 px-3.5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold">{METRIC_LABEL[r.metric_name] ?? r.metric_name}</span>
                    {r.passed != null && (
                      <Chip color={color}>{r.passed ? "đạt ngưỡng" : "chưa đạt"}</Chip>
                    )}
                    {lower && <span className="text-2xs text-ink-low">thấp hơn là tốt hơn</span>}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-low">{METRIC_HINT[r.metric_name] ?? ""}</p>
                </div>
                <div className="flex flex-none items-baseline gap-4">
                  <div className="text-right">
                    <div className="text-2xs text-ink-low">Đạt được</div>
                    <div className="tabular font-mono text-4xl font-semibold" style={{ color }}>
                      {r.metric_value.toFixed(r.metric_value > 1 ? 1 : 3)}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xs text-ink-low">Ngưỡng</div>
                    <div className="tabular font-mono text-2xl text-ink-soft">
                      {r.target_value != null ? r.target_value.toFixed(r.target_value > 1 ? 1 : 3) : "—"}
                    </div>
                  </div>
                </div>
              </div>
              {ratio != null && (
                <div className="px-3.5 pb-3">
                  <ProgressBar value={ratio} color={color} />
                  <div className="mt-1 flex justify-between text-3xs text-ink-dim">
                    <span>
                      {r.task_id} · tập {r.split}
                    </span>
                    <span>đánh giá {formatDateTime(r.evaluated_at)}</span>
                  </div>
                </div>
              )}
            </Panel>
          );
        })}
      </div>

      <Panel title="Vì sao không có độ chính xác tổng thể" subtitle="Chương 15.1 của tài liệu thiết kế">
        <p className="text-xs leading-relaxed text-ink-soft">
          Với tỷ lệ dương thật cỡ phần nghìn, một mô hình trả lời{" "}
          <b className="text-ink-mid">"không có gì bất thường"</b> cho mọi giao dịch vẫn đạt độ chính xác tổng thể trên 99%. Con số
          đó không nói gì về việc hệ thống có dùng được hay không.
        </p>
        <p className="mt-2 text-xs leading-relaxed text-ink-low">
          Ba chỉ số quyết định giá trị vận hành: thứ tự ưu tiên có đúng không (precision@k), phát hiện sớm được bao lâu
          trước khi đủ bằng chứng (thời gian phát hiện sớm), và gắn cờ nhầm bao nhiêu trên nhóm hợp pháp trông giống đối tượng nghi
          vấn (dương tính giả trên mẫu âm khó). Thiếu nhóm mẫu âm khó thì cả ba chỉ số đều mất ý nghĩa.
        </p>
      </Panel>
    </PageShell>
  );
}
