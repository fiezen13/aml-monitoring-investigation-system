import { useMemo } from "react";

import { api } from "../api/client";
import { int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { Panel } from "../components/fc/primitives";
import { KpiCard, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { GrafanaCockpit } from "../components/observability/GrafanaCockpit";
import { PageShell } from "../components/ui";
import { C } from "../design/palette";

/** Audited benchmark plus the exact model release currently served by the UI. */
const DRIFT_STATUS: Record<string, { label: string; color: string }> = {
  healthy: { label: "Ổn định", color: C.ok },
  watch: { label: "Cần theo dõi", color: C.warn },
  degraded: { label: "Đã lệch", color: C.risk },
};

export function ModelsPage() {
  const release = useApi(() => api.edgeModelRelease(), []);
  const monitor = useApi(() => api.modelMonitor(), []);
  const primary = release.data?.benchmark.primary_seed;
  const seeded = release.data?.benchmark.over_seeds;
  const alertRate = release.data
    ? (release.data.triggered_rows / release.data.transaction_rows) * 100
    : null;

  /**
   * Gộp các chỉ số giám sát về từng tuần dữ liệu.
   *
   * Backend trả một dòng cho mỗi (tuần, chỉ số) vì đó là dạng lưu tự nhiên;
   * người đọc thì cần một dòng cho mỗi tuần. Gộp ở đây thay vì tạo thêm một
   * endpoint chỉ để đổi hình dạng.
   */
  const weeks = useMemo(() => {
    const byWeek = new Map<string, { at: string; status: string; drift: number | null; metrics: Record<string, number> }>();
    for (const row of monitor.data ?? []) {
      const entry = byWeek.get(row.observed_at) ?? {
        at: row.observed_at,
        status: row.status,
        drift: row.drift_score,
        metrics: {},
      };
      entry.metrics[row.metric_name] = row.metric_value;
      byWeek.set(row.observed_at, entry);
    }
    return [...byWeek.values()].sort((a, b) => a.at.localeCompare(b.at));
  }, [monitor.data]);

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Mô hình đang phục vụ"
        meta="Artifact, benchmark và policy contract của đúng release nối vào giao diện"
      />

      {release.loading ? (
        <Skeleton rows={2} />
      ) : release.error ? (
        <div className="rounded border border-risk/30 bg-risk/5 px-4 py-3 text-sm text-risk-soft">
          {release.error}
        </div>
      ) : (
        <>
          <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Phiên bản model"
              value={release.data?.model_version ?? "—"}
              valueColor={C.inkHi}
              delta={`${release.data?.status ?? "—"} · ${release.data?.feature_count ?? 0} features`}
            />
            <KpiCard
              label="F1 · 5 seeds"
              value={seeded ? seeded.f1_mean.toFixed(4) : "—"}
              valueColor={C.ok}
              delta={seeded ? `sample std ±${seeded.f1_sample_std.toFixed(4)}` : "—"}
            />
            <KpiCard
              label="PR-AUC · seed 42"
              value={typeof primary?.pr_auc === "number" ? primary.pr_auc.toFixed(4) : "—"}
              valueColor={C.ok}
              delta={
                typeof primary?.precision === "number" && typeof primary?.recall === "number"
                  ? `P ${primary.precision.toFixed(4)} · R ${primary.recall.toFixed(4)}`
                  : "—"
              }
            />
            <KpiCard
              label="Cảnh báo / giao dịch test"
              value={release.data ? int(release.data.triggered_rows) : "—"}
              valueColor={C.warn}
              delta={
                alertRate == null
                  ? "—"
                  : `${alertRate.toFixed(4)}% trên ${int(release.data!.transaction_rows)} dòng`
              }
            />
          </div>

          <Panel title="Currency-native policy contract" bodyClassName="space-y-3">
            <div className="grid gap-3 text-xs text-ink-soft md:grid-cols-2 xl:grid-cols-4">
              <div>
                <div className="text-3xs uppercase tracking-wider text-ink-low">Amount Paid</div>
                <div className="mt-1 text-ink-hi">Giữ nguyên giá trị và payment currency gốc</div>
              </div>
              <div>
                <div className="text-3xs uppercase tracking-wider text-ink-low">Amount Received</div>
                <div className="mt-1 text-ink-hi">Giữ nguyên giá trị và receiving currency gốc</div>
              </div>
              <div>
                <div className="text-3xs uppercase tracking-wider text-ink-low">Chuẩn hoá</div>
                <div className="mt-1 text-ink-hi">Train-only log1p z-score theo từng currency</div>
              </div>
              <div>
                <div className="text-3xs uppercase tracking-wider text-ink-low">FX trong ML</div>
                <div className="mt-1 text-ink-hi">Không dùng static FX; luật USD nằm ngoài model</div>
              </div>
            </div>
            <div className="border-t border-line-faint pt-3 font-mono text-2xs text-ink-low">
              <div>release: {release.data?.release_id}</div>
              <div>model sha256: {release.data?.model_sha256}</div>
              <div>scores sha256: {release.data?.scores_sha256}</div>
              <div>
                trained: {release.data ? formatDateTime(release.data.trained_at) : "—"} · activated:{" "}
                {release.data?.activated_at ? formatDateTime(release.data.activated_at) : "—"}
              </div>
            </div>
          </Panel>
        </>
      )}

      <Panel
        title="Trôi phân phối điểm theo tuần"
        subtitle="PSI so với tuần đầu tiên của bộ dữ liệu. Dưới 0,1 coi như không đổi; trên 0,25 là đã lệch"
        bodyClassName="space-y-2"
      >
        {monitor.loading && <Skeleton rows={3} />}
        {!monitor.loading && !weeks.length && (
          <p className="text-xs text-ink-low">
            Chưa có số liệu giám sát. Chạy <span className="font-mono">python -m scripts.run_data_quality</span> để
            tính lại từ điểm số đã lưu.
          </p>
        )}
        {weeks.map((w) => {
          const tone = DRIFT_STATUS[w.status] ?? { label: w.status, color: C.inkSoft };
          return (
            <div
              key={w.at}
              className="grid items-baseline gap-2 border-b border-line-faint pb-2 text-xs last:border-0 last:pb-0"
              style={{ gridTemplateColumns: "120px 110px 1fr 1fr 1fr" }}
            >
              <span className="font-mono text-ink-hi">{w.at.slice(0, 10)}</span>
              <span className="font-semibold" style={{ color: tone.color }}>
                {tone.label}
              </span>
              {/* Tuần đầu là mốc tham chiếu nên không có PSI — dấu gạch, không phải số 0. */}
              <span className="tabular font-mono text-ink-soft">
                PSI {w.drift == null ? "—" : w.drift.toFixed(4)}
              </span>
              <span className="tabular font-mono text-ink-soft">
                gắn cờ {((w.metrics.alert_rate ?? 0) * 100).toFixed(4)}%
              </span>
              <span className="tabular font-mono text-ink-low">{int(w.metrics.scored_rows ?? 0)} giao dịch</span>
            </div>
          );
        })}
      </Panel>

      <GrafanaCockpit />
    </PageShell>
  );
}
