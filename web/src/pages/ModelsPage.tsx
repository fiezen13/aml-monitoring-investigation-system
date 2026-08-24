import { api } from "../api/client";
import { int } from "../api/fcFormat";
import { formatDateTime } from "../api/format";
import { useApi } from "../api/useApi";
import { Panel, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { ObservabilityPanel } from "../components/observability/ObservabilityPanel";
import { PageShell } from "../components/ui";

/**
 * Giám sát mô hình — kiểm kê TẤT CẢ nhánh mô hình đang triển khai.
 *
 * Một nhánh 'active' đang chấm điểm cho hàng đợi chính; các nhánh còn lại là
 * 'reference' (Bitcoin, SAML-D). Mỗi nhánh đo trên đúng vùng của nó bằng model
 * riêng — KHÔNG cộng gộp điểm. Chi tiết đối chiếu hiệu năng nằm ở Đánh giá chuẩn;
 * ở đây là kiểm kê + truy xuất + quan sát vận hành.
 */

const KIND_LABEL: Record<string, string> = {
  graph_edge_classifier: "Mạng đồ thị chấm cạnh",
  random_forest_classifier: "Random Forest",
  geo_rule_ranker: "Bộ luật địa lý xếp hạng",
};

function fmtMetric(m: { value: number; kind: string }): string {
  return m.kind === "multiple" ? `${m.value.toFixed(2)}×` : m.value.toFixed(4);
}

export function ModelsPage() {
  const branches = useApi(() => api.modelBranches(), [], "model-branches");
  const release = useApi(() => api.edgeModelRelease(), [], "edge-model-release");
  // Bỏ nhánh luật địa lý (geo_rule_ranker) khỏi trang này: nó là BỘ LUẬT tất định,
  // không phải model ML để giám sát ở đây (vẫn có ở Đánh giá chuẩn và bản đồ địa
  // lý). Còn lại đúng ba nhánh model — IBM, Bitcoin, SAML-D (đồ thị) — mỗi bộ một thẻ.
  const list = (branches.data ?? []).filter((b) => b.model_kind !== "geo_rule_ranker");

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Giám sát mô hình"
        meta="Ba nhánh mô hình đang phục vụ, mỗi nhánh chấm điểm cho mặt hàng riêng (ngân hàng · tài sản mã hoá · SAML-D). Mỗi nhánh đo trên vùng đặc trưng, không cộng gộp điểm."
      />

      {branches.loading && <Skeleton rows={3} />}
      {branches.error && (
        <div className="rounded border border-risk/30 bg-risk/5 px-4 py-3 text-sm text-risk-soft">
          {branches.error}
        </div>
      )}

      {/* Kiểm kê nhánh: IBM (đang phục vụ), Bitcoin, SAML-D — mỗi nhánh một thẻ. */}
      <div className="grid gap-2.5 lg:grid-cols-2 xl:grid-cols-3">
        {list.map((b) => {
          return (
            <div key={b.release_id} className="rounded-panel border border-line bg-sunken p-3.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-semibold text-ink-hi">{b.region_label}</span>
                {/* Cả ba nhánh đều ĐANG PHỤC VỤ — mỗi nhánh chấm điểm cho mặt hàng
                    riêng (IBM: hàng đợi ngân hàng · Bitcoin: tài sản mã hoá ·
                    SAML-D: hàng đợi SAML-D). 'active/reference' chỉ là chi tiết kỹ
                    thuật của một slot edge-release, không phải "nhánh kia không chạy". */}
                <span className="flex-none rounded-control bg-ok/15 px-2 py-0.5 text-3xs font-medium text-ok">
                  Đang phục vụ
                </span>
              </div>
              <div className="mt-0.5 text-2xs text-ink-low">{b.dataset}</div>
              <div className="mt-2 font-mono text-xs text-ink-soft">{b.model_version}</div>
              <div className="text-3xs text-ink-low">{KIND_LABEL[b.model_kind] ?? b.model_kind}</div>

              {b.headline.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 border-t border-line-faint pt-2.5">
                  {b.headline.map((m) => (
                    <div key={m.label}>
                      <div className="text-3xs uppercase tracking-wide text-ink-low">{m.label}</div>
                      <div className="tabular font-mono text-sm text-ok">{fmtMetric(m)}</div>
                    </div>
                  ))}
                </div>
              )}

              <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-0.5 border-t border-line-faint pt-2 text-2xs text-ink-low">
                <span>{int(b.region_rows ?? 0)} dòng trong vùng</span>
                <span>{int(b.triggered_rows)} gắn cờ</span>
                {b.positive_rate != null && <span>{(b.positive_rate * 100).toFixed(3)}% nhãn dương</span>}
              </div>
            </div>
          );
        })}
      </div>

      {/* Chi tiết truy xuất của nhánh IBM MEGA-PNA (bản phát hành đã ký): hợp đồng
          chuẩn hoá currency-native + chữ ký model/scores để đối chiếu đúng bản. */}
      {release.data && (
        <Panel title={`Hợp đồng & truy xuất — ${release.data.dataset}`} bodyClassName="space-y-3">
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
            <div>release: {release.data.release_id}</div>
            <div>model sha256: {release.data.model_sha256}</div>
            <div>scores sha256: {release.data.scores_sha256}</div>
            <div>
              trained: {formatDateTime(release.data.trained_at)} · activated:{" "}
              {release.data.activated_at ? formatDateTime(release.data.activated_at) : "—"}
            </div>
          </div>
        </Panel>
      )}

      <ObservabilityPanel />
    </PageShell>
  );
}
