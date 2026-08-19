import type { ModelBranch } from "../../api/client";
import { int } from "../../api/fcFormat";
import { C } from "../../design/palette";
import { Eyebrow, Panel } from "./primitives";

/**
 * Đối chiếu các nhánh phát hiện — mỗi nhánh trên vùng đặc trưng của nó.
 *
 * Kiến trúc của hệ thống là nhiều nhánh song song: IBM HI-Medium bắt rửa tiền
 * qua giao dịch TRONG ngân hàng (mạng đồ thị MEGA-PNA), SAML-D bắt rửa tiền
 * XUYÊN BIÊN GIỚI (bộ luật địa lý), sắp tới Elliptic++ bắt rửa tiền bitcoin.
 *
 * Ba nhánh KHÔNG cộng gộp thành một con số, và màn hình này cố tình không cho
 * làm thế: mỗi thẻ tự khai vùng đo, loại model, và bộ chỉ số của riêng nó. Một
 * F1 chung sẽ là lời nói dối — MEGA-PNA chấm từng cạnh nên có F1/PR-AUC, còn
 * geo_rule xếp hạng theo ngân sách nên chỉ có precision/recall/lift @ ngân sách.
 */

const KIND_META: Record<string, { label: string; color: string }> = {
  graph_edge_classifier: { label: "Mạng đồ thị · chấm từng cạnh", color: C.agent },
  geo_rule_ranker: { label: "Bộ luật · xếp hạng theo ngân sách", color: C.info },
  random_forest_classifier: { label: "Random Forest · chấm từng giao dịch", color: C.risk },
};

const STATUS_META: Record<string, { label: string; color: string }> = {
  active: { label: "Đang chấm điểm", color: C.ok },
  reference: { label: "Nhánh tham chiếu", color: C.info },
};

function pct(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toFixed(3)}%`;
}

export function ModelBranchCards({ branches }: { branches: ModelBranch[] }) {
  if (!branches.length) return null;
  const note = branches.find((b) => b.not_comparable_note)?.not_comparable_note;

  return (
    <div className="animate-up">
      <div className="mb-2.5 rounded-panel border border-line bg-sunken px-4 py-3">
        <Eyebrow>Ba nhánh, ba vùng đặc trưng — đo riêng, không cộng gộp</Eyebrow>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-soft">
          Mỗi bộ dữ liệu có model và benchmark riêng, đo trên đúng vùng nó đặc trưng cho. {note}
        </p>
      </div>

      <div className="grid gap-2.5 lg:grid-cols-2">
        {branches.map((b) => {
          const kind = KIND_META[b.model_kind] ?? { label: b.model_kind, color: C.inkSoft };
          const status = STATUS_META[b.status] ?? { label: b.status, color: C.inkSoft };
          return (
            <Panel key={b.release_id} className="p-0">
              <div className="border-b border-line px-3.5 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-lg font-semibold text-ink-hi">{b.region_label}</div>
                    <div className="mt-0.5 font-mono text-2xs text-ink-low">{b.dataset}</div>
                  </div>
                  <span
                    className="flex-none rounded-control px-2 py-0.5 text-3xs font-medium"
                    style={{ color: status.color, background: `${status.color}1a` }}
                  >
                    {status.label}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-1.5">
                  <span className="size-1.5 flex-none rounded-full" style={{ background: kind.color }} />
                  <span className="text-2xs text-ink-soft">{kind.label}</span>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-ink-low">{b.region_description}</p>
              </div>

              {/* Vùng đo — nói rõ đo trên bao nhiêu, tỉ lệ dương thật bao nhiêu. */}
              <div className="grid grid-cols-3 gap-2 border-b border-line-faint px-3.5 py-2.5 text-center">
                <div>
                  <div className="text-3xs uppercase tracking-wide text-ink-low">Dòng trong vùng</div>
                  <div className="tabular mt-0.5 font-mono text-sm text-ink-hi">{int(b.region_rows ?? 0)}</div>
                </div>
                <div>
                  <div className="text-3xs uppercase tracking-wide text-ink-low">Nhãn dương</div>
                  <div className="tabular mt-0.5 font-mono text-sm text-ink-hi">{int(b.positive_rows ?? 0)}</div>
                </div>
                <div>
                  <div className="text-3xs uppercase tracking-wide text-ink-low">Tỉ lệ dương</div>
                  <div className="tabular mt-0.5 font-mono text-sm" style={{ color: C.warn }}>
                    {pct(b.positive_rate)}
                  </div>
                </div>
              </div>

              {/* Chỉ số đầu bảng — đã chọn theo loại model, nên hai nhánh hiện
                  hai bộ khác nhau. Đó là chủ ý, không phải thiếu sót. */}
              <div className="flex flex-wrap gap-x-5 gap-y-2 px-3.5 py-3">
                {b.headline.map((h) => (
                  <div key={h.label}>
                    <div className="text-3xs uppercase tracking-wide text-ink-low">{h.label}</div>
                    <div className="tabular font-mono text-2xl font-semibold" style={{ color: kind.color }}>
                      {h.kind === "multiple" ? `${h.value.toFixed(2)}×` : h.value.toFixed(4)}
                    </div>
                  </div>
                ))}
              </div>

              {/* Đường vận hành: cùng dạng cho cả hai nhánh, nên đọc được song
                  song — dù vẫn là hai vùng khác nhau. */}
              {b.operating_points.length > 0 && (
                <div className="border-t border-line-faint px-3.5 py-3">
                  <div className="mb-1.5 text-3xs uppercase tracking-wide text-ink-low">
                    Bắt được bao nhiêu theo ngân sách cảnh báo
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-2xs">
                      <thead>
                        <tr className="text-ink-dim">
                          <th className="py-1 pr-3 text-left font-medium">Ngân sách</th>
                          <th className="py-1 pr-3 text-right font-medium">Bắt đúng</th>
                          <th className="py-1 pr-3 text-right font-medium">Precision</th>
                          <th className="py-1 pr-3 text-right font-medium">Recall</th>
                          {b.operating_points.some((p) => p.lift != null) && (
                            <th className="py-1 text-right font-medium">Lift</th>
                          )}
                        </tr>
                      </thead>
                      <tbody className="font-mono text-ink-soft">
                        {b.operating_points.map((p) => (
                          <tr key={p.alerts} className="border-t border-line-faint/60">
                            <td className="py-1 pr-3 text-left">{int(p.alerts)}</td>
                            <td className="tabular py-1 pr-3 text-right">{int(p.caught)}</td>
                            <td className="tabular py-1 pr-3 text-right">{(p.precision * 100).toFixed(1)}%</td>
                            <td className="tabular py-1 pr-3 text-right">{(p.recall * 100).toFixed(1)}%</td>
                            {b.operating_points.some((q) => q.lift != null) && (
                              <td className="tabular py-1 text-right" style={{ color: C.info }}>
                                {p.lift == null ? "—" : `${p.lift.toFixed(1)}×`}
                              </td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
