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
export function ModelsPage() {
  const release = useApi(() => api.edgeModelRelease(), []);
  const primary = release.data?.benchmark.primary_seed;
  const seeded = release.data?.benchmark.over_seeds;
  const alertRate = release.data
    ? (release.data.triggered_rows / release.data.transaction_rows) * 100
    : null;

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

      <GrafanaCockpit />
    </PageShell>
  );
}
