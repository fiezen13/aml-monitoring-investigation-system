import { useMemo } from "react";

import { api } from "../api/client";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { ErrorState, PageShell } from "../components/ui";
import { type ChartSpec } from "../components/fc/Chart";
import { ChartCard } from "../components/fc/ChartCard";
import { ModelBranchCards } from "../components/fc/ModelBranchCards";
import { Empty, KpiCard, Panel, ProgressBar, ScreenTitle, Skeleton } from "../components/fc/primitives";
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

/**
 * Năm chỉ số lấy ra từ khối benchmark đã ký của release. Tên viết đúng như
 * trong dữ liệu — đổi tên ở đây là nói dối về nguồn.
 */
const METRIC_LABEL: Record<string, string> = {
  f1: "F1",
  pr_auc: "PR-AUC",
  precision: "Độ chính xác",
  recall: "Độ bao phủ",
  alert_rate: "Tỷ lệ gắn cờ",
};

const METRIC_HINT: Record<string, string> = {
  f1: "Trung bình điều hòa giữa độ chính xác và độ bao phủ. Một con số gộp cả hai mặt.",
  pr_auc:
    "Diện tích dưới đường precision-recall. Với dữ liệu lệch lớp nặng như rửa tiền, chỉ số này trung thực hơn ROC-AUC.",
  precision: "Trong các giao dịch bị gắn cờ, bao nhiêu phần thực sự là rửa tiền.",
  recall: "Trong toàn bộ giao dịch rửa tiền, bao nhiêu phần bị gắn cờ.",
  alert_rate:
    "Phần giao dịch bị gắn cờ trên tổng số. Thấp mới là tốt: mỗi cảnh báo là một giờ công của chuyên viên.",
};

/** Với chỉ số này, giá trị thấp mới là tốt: mỗi cảnh báo tốn một giờ công. */
const LOWER_IS_BETTER = new Set(["alert_rate"]);

/** Thứ tự trình bày; cũng là thứ tự quan trọng khi đọc một bản đánh giá. */
const METRIC_ORDER = ["f1", "pr_auc", "precision", "recall", "alert_rate"];

interface Aggregate {
  metric: string;
  values: number[];
  mean: number;
  min: number;
  max: number;
  std: number;
}

function aggregate(values: number[]): Omit<Aggregate, "metric" | "values"> {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  // Độ lệch chuẩn mẫu (chia n-1): năm seed là một mẫu rút từ tập vô hạn các
  // lần khởi tạo, không phải toàn bộ tổng thể.
  const variance =
    values.length > 1 ? values.reduce((a, b) => a + (b - mean) ** 2, 0) / (values.length - 1) : 0;
  return { mean, min: Math.min(...values), max: Math.max(...values), std: Math.sqrt(variance) };
}

export function BenchmarksPage() {
  const data = useApi(() => api.benchmarks(), [], "benchmarks");
  const branchData = useApi(() => api.modelBranches(), [], "model-branches");
  const rows = data.data ?? [];
  // Bỏ nhánh luật địa lý (geo_rule_ranker) khỏi trang này — giống ModelsPage:
  // nó là BỘ LUẬT tất định xếp hạng theo ngân sách, không phải model học máy,
  // nên card benchmark của nó gây nhiễu ở màn đánh giá mô hình.
  const branches = (branchData.data ?? []).filter((b) => b.model_kind !== "geo_rule_ranker");

  /**
   * Gộp theo chỉ số, giữ lại từng giá trị.
   *
   * Bản phát hành chạy trên năm seed độc lập. Một con số F1 duy nhất không phân
   * biệt được "mô hình tốt" với "một lần chạy may mắn", nên màn hình này bày cả
   * dải giá trị và độ lệch chuẩn — chính độ lệch ấy mới nói mô hình có ổn định.
   */
  const metrics = useMemo<Aggregate[]>(() => {
    const byMetric = new Map<string, number[]>();
    for (const r of rows) {
      const list = byMetric.get(r.metric_name) ?? [];
      list.push(r.metric_value);
      byMetric.set(r.metric_name, list);
    }
    return METRIC_ORDER.filter((m) => byMetric.has(m)).map((metric) => {
      const values = byMetric.get(metric)!;
      return { metric, values, ...aggregate(values) };
    });
  }, [rows]);

  const primary = rows.filter((r) => r.task_id.includes("chính"));
  const primaryOf = (metric: string) => primary.find((r) => r.metric_name === metric)?.metric_value;
  const f1 = metrics.find((m) => m.metric === "f1");

  /** Mỗi cột là một seed; đọc ngang thấy ngay mô hình dao động bao nhiêu. */
  const spec = useMemo<ChartSpec | null>(() => {
    const seeds = [...new Set(rows.map((r) => r.task_id))];
    if (seeds.length < 2) return null;
    const seriesFor = (metric: string) =>
      seeds.map((seed) => rows.find((r) => r.task_id === seed && r.metric_name === metric)?.metric_value ?? 0);
    return {
      type: "bars",
      labels: seeds.map((s) => s.replace(" (chính)", "*")),
      series: [
        { name: "F1", data: seriesFor("f1"), color: C.primary },
        { name: "PR-AUC", data: seriesFor("pr_auc"), color: C.agent },
      ],
    };
  }, [rows]);

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Đánh giá chuẩn"
        meta="Mỗi nhánh có model và benchmark riêng, đo trên đúng vùng nó đặc trưng — không cộng gộp"
      />

      {branchData.loading && <Skeleton rows={4} />}
      {branchData.error && <ErrorState detail={branchData.error} onRetry={branchData.reload} />}
      <ModelBranchCards branches={branches} />

      {/* Phần dưới đây đi sâu vào ĐỘ ỔN ĐỊNH của riêng nhánh IBM: mô hình đồ thị
          chạy nhiều seed, và độ lệch giữa các seed mới nói mô hình chắc hay ăn
          may. Nhánh geo_rule là bộ luật tất định nên không có khái niệm seed. */}
      <ScreenTitle
        title="Chi tiết ổn định — nhánh IBM (MEGA-PNA)"
        meta="Kết quả đã ký của nhánh IBM MEGA-PNA — mô hình đồ thị chấm cạnh trên HI-Medium (nhánh tham chiếu chất lượng cao, không phải bộ luật đang phục vụ hàng đợi)"
      />

      <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
        <KpiCard
          label="F1 seed chính"
          value={primaryOf("f1")?.toFixed(4) ?? "—"}
          valueColor={C.primary}
          delta="seed phát hành"
        />
        <KpiCard
          label="F1 trung bình"
          value={f1 ? f1.mean.toFixed(4) : "—"}
          delta={f1 ? `${f1.values.length} seed độc lập` : ""}
        />
        <KpiCard
          label="Độ lệch chuẩn F1"
          value={f1 ? f1.std.toFixed(4) : "—"}
          valueColor={f1 && f1.std > 0.05 ? C.warn : C.ok}
          delta="càng thấp càng ổn định"
        />
        <KpiCard
          label="Phiên bản mô hình"
          value={<span className="text-2xl">{rows[0]?.model_version ?? "—"}</span>}
          delta={rows[0] ? `${rows[0].scenario_package} · tập ${rows[0].split}` : ""}
        />
      </div>

      <ChartCard
        title="F1 và PR-AUC theo từng seed"
        subtitle="Dấu * là seed phát hành. Khoảng cách giữa các cột chính là mức dao động của mô hình"
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
          hint="Chạy pipeline benchmark đã khóa split và threshold, sau đó nạp release bằng scripts/load_currency_native_edge_release.py."
        />
      )}

      <div className="flex flex-col gap-2.5">
        {metrics.map((m) => {
          const lower = LOWER_IS_BETTER.has(m.metric);
          // Thanh chỉ mô tả vị trí trung bình trên thang 0–1, không so với
          // ngưỡng nào: bản phát hành này không chốt trước mục tiêu, và vẽ ra
          // một ngưỡng để mọi dòng đều xanh là tự lừa mình.
          const width = Math.min(100, m.mean * 100);
          return (
            <Panel key={m.metric} className="p-0">
              <div className="flex flex-wrap items-start gap-3 px-3.5 py-3">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-base font-semibold">{METRIC_LABEL[m.metric] ?? m.metric}</span>
                    {lower && <span className="text-2xs text-ink-low">thấp hơn là tốt hơn</span>}
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-low">{METRIC_HINT[m.metric] ?? ""}</p>
                </div>
                <div className="flex flex-none items-baseline gap-4">
                  <div className="text-right">
                    <div className="text-2xs text-ink-low">Seed chính</div>
                    <div className="tabular font-mono text-4xl font-semibold" style={{ color: C.primary }}>
                      {primaryOf(m.metric)?.toFixed(4) ?? "—"}
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xs text-ink-low">Dải {m.values.length} seed</div>
                    <div className="tabular font-mono text-2xl text-ink-soft">
                      {m.min.toFixed(4)} – {m.max.toFixed(4)}
                    </div>
                  </div>
                </div>
              </div>
              <div className="px-3.5 pb-3">
                <ProgressBar value={width} color={lower ? C.warn : C.primary} />
                <div className="mt-1 flex justify-between text-3xs text-ink-dim">
                  <span>
                    trung bình {m.mean.toFixed(4)} · độ lệch chuẩn {m.std.toFixed(4)}
                  </span>
                  <span>đánh giá {formatDateTime(rows[0]?.evaluated_at ?? "")}</span>
                </div>
              </div>
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
