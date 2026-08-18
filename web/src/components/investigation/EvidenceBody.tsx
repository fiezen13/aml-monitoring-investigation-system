/** Hiển thị bằng chứng bằng ngôn ngữ chuyên viên đọc được.
 *
 * Trước đây khối này đổ thẳng `JSON.stringify(payload)` ra màn hình. Chuyên viên
 * tuân thủ phải đọc `"median_dwell_time": 999.0` rồi tự đoán đơn vị, hoặc đọc
 * `"components": {"graph": {"contribution": 0.9995}}` rồi tự hiểu điểm rủi ro
 * đến từ đâu. Đó không phải giải thích, đó là đổ dữ liệu ra màn hình.
 *
 * JSON gốc **không bị bỏ** — nó vẫn nằm sau nút "Dữ liệu gốc". Bằng chứng phải
 * kiểm chứng được, và tác tử phản biện đối chiếu chính chuỗi ấy; giấu đi là làm
 * hỏng khả năng truy vết.
 */

import { useState } from "react";
import { formatDateTime, riskComponentLabel } from "../../api/format";
import { FEATURE_GROUPS, featureMeta, formatFeature } from "../../api/behaviorLabels";

type Payload = Record<string, unknown>;

const num = (v: unknown): number | null => (typeof v === "number" ? v : null);
const pct = (v: number): string => `${(v * 100).toFixed(2)}%`;

function Line({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line/40 py-1 last:border-0">
      <span className="text-2xs text-ink-mid" title={hint}>
        {label}
        {hint && <span className="ml-1 text-ink-low">ⓘ</span>}
      </span>
      <span className="tabular text-2xs font-medium text-ink-hi">{value}</span>
    </div>
  );
}

function Lead({ children }: { children: React.ReactNode }) {
  return <p className="mb-2 text-2xs leading-relaxed text-ink-hi">{children}</p>;
}

/** Điểm rủi ro đến từ nhánh nào, và nhánh nào không có dữ liệu. */
function RiskBreakdown({ p }: { p: Payload }) {
  const components = (p.components ?? {}) as Record<string, Payload>;
  const final = num(p.final_risk_score);
  const active = Object.entries(components).filter(([, c]) => c.available === true);
  const missing = Object.entries(components).filter(([, c]) => c.available !== true);

  return (
    <div>
      <Lead>
        {final !== null ? <>Điểm rủi ro cuối cùng <b>{pct(final)}</b>. </> : null}
        {active.length === 1 ? (
          <>Toàn bộ điểm đến từ nhánh <b>{riskComponentLabel(active[0][0])}</b>.</>
        ) : active.length > 1 ? (
          <>Điểm hợp nhất từ {active.length} nhánh.</>
        ) : (
          <>Không nhánh nào có dữ liệu để phân rã.</>
        )}
      </Lead>
      {active.map(([name, c]) => (
        <Line
          key={name}
          label={`Nhánh ${riskComponentLabel(name)}`}
          value={`${num(c.score) !== null ? pct(num(c.score)!) : "—"} · trọng số ${num(c.weight) ?? "—"}`}
        />
      ))}
      {missing.length > 0 && (
        <p className="mt-2 text-micro text-ink-low">
          Không có dữ liệu: {missing.map(([n]) => riskComponentLabel(n)).join(", ")}. Nhánh thiếu dữ liệu được ghi là
          không khả dụng chứ không suy đoán giá trị.
        </p>
      )}
    </div>
  );
}

/** Luật nào đã kích hoạt, và mức đóng góp của từng luật. */
function RuleTrigger({ p }: { p: Payload }) {
  const all = (p.triggered_rules ?? []) as Payload[];
  // CTX_* mang trọng số 0 — chúng là số đo ngữ cảnh, không phải luật. Trộn chung
  // khiến người đọc tưởng có nhiều luật kích hoạt hơn thực tế.
  const rules = all.filter((r) => !String(r.factor_code ?? "").startsWith("CTX_"));
  const context = all.filter((r) => String(r.factor_code ?? "").startsWith("CTX_"));

  return (
    <div>
      <Lead>
        {rules.length > 0 ? (
          <>
            <b>{rules.length}</b> luật kích hoạt trên tài khoản này.
          </>
        ) : (
          <>Không có luật nào kích hoạt.</>
        )}
      </Lead>
      {rules.map((r, i) => (
        <Line
          key={i}
          label={String(r.factor_label ?? r.factor_code)}
          value={`đóng góp ${r.contribution}/100 · trọng số ${r.weight}`}
        />
      ))}
      {context.length > 0 && (
        <p className="mt-2 text-micro text-ink-low">
          Kèm {context.length} số đo ngữ cảnh (trọng số 0, không góp vào điểm):{" "}
          {context.map((c) => String(c.factor_label ?? c.factor_code)).join("; ")}.
        </p>
      )}
    </div>
  );
}

/** Đặc trưng hành vi, nhóm lại và dịch sang tiếng Việt kèm đơn vị. */
function BehaviorFeature({ p }: { p: Payload }) {
  const features = (p.features ?? {}) as Record<string, unknown>;
  const shown = new Set<string>();

  return (
    <div>
      <Lead>
        Số liệu hành vi của tài khoản trong cửa sổ <b>{String(p.window ?? "—")}</b>.
      </Lead>
      {FEATURE_GROUPS.map((group) => {
        const keys = group.keys.filter((k) => k in features);
        keys.forEach((k) => shown.add(k));
        if (!keys.length) return null;
        return (
          <div key={group.title} className="mb-2">
            <h5 className="mb-1 text-micro font-semibold uppercase tracking-wider text-ink-low">{group.title}</h5>
            {keys.map((k) => {
              const meta = featureMeta(k);
              return <Line key={k} label={meta.label} value={formatFeature(features[k], meta.format)} hint={meta.hint} />;
            })}
          </div>
        );
      })}
      {Object.keys(features)
        .filter((k) => !shown.has(k))
        .map((k) => {
          const meta = featureMeta(k);
          return <Line key={k} label={meta.label} value={formatFeature(features[k], meta.format)} hint={meta.hint} />;
        })}
    </div>
  );
}

/** Đặc trưng nào lệch xa nhất so với phần còn lại. */
function AnomalyExplanation({ p }: { p: Payload }) {
  const top = (p.top_anomalous_features ?? []) as Payload[];
  const score = num(p.anomaly_score);
  if (p.available === false) {
    return <Lead>Không có giải thích bất thường cho cảnh báo này: {String(p.missing_reason ?? "nguồn không khả dụng")}.</Lead>;
  }
  return (
    <div>
      <Lead>
        Điểm bất thường <b>{score !== null ? score.toFixed(2) : "—"}</b>. Các đặc trưng dưới đây lệch xa nhất so với
        những tài khoản khác trong cùng cửa sổ.
      </Lead>
      {top.map((f, i) => {
        const meta = featureMeta(String(f.feature));
        const p100 = num(f.reference_percentile);
        return (
          <Line
            key={i}
            label={meta.label}
            value={`${formatFeature(f.value, meta.format)}${p100 !== null ? ` · cao hơn ${p100}% tài khoản` : ""}`}
            hint={meta.hint}
          />
        );
      })}
      <p className="mt-2 text-micro text-ink-low">Cách tính: {String(p.method ?? "—")}.</p>
    </div>
  );
}

/** Danh sách giao dịch, dạng bảng thay vì mảng JSON. */
function Transactions({ p }: { p: Payload }) {
  const items = (p.items ?? []) as Payload[];
  return (
    <div>
      <Lead>
        <b>{items.length}</b> giao dịch được dùng làm bằng chứng.
      </Lead>
      <div className="overflow-x-auto">
        <table className="w-full text-micro">
          <thead>
            <tr className="text-ink-low">
              <th className="py-1 text-left font-medium">Thời điểm</th>
              <th className="text-left font-medium">Từ</th>
              <th className="text-left font-medium">Đến</th>
              <th className="text-right font-medium">Số tiền</th>
              <th className="text-left font-medium">Hình thức</th>
            </tr>
          </thead>
          <tbody>
            {items.map((t, i) => (
              <tr key={i} className="border-t border-line/40">
                <td className="py-1 text-ink-mid">{formatDateTime(String(t.timestamp))}</td>
                <td className="tabular text-ink-mid">{String(t.source)}</td>
                <td className="tabular text-ink-mid">{String(t.destination)}</td>
                <td className="tabular text-right text-ink-hi">
                  {Number(t.amount).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} {String(t.currency ?? "")}
                </td>
                <td className="text-ink-mid">{String(t.payment_format ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Cụm giao dịch tạo thành hình dạng có tên. */
function GraphShape({ p, neighborhood }: { p: Payload; neighborhood: boolean }) {
  const edges = (p.edges ?? []) as Payload[];
  const accounts = (p.accounts ?? []) as string[];
  const length = num(p.cycle_length);
  const hours = num(p.duration_hours);

  return (
    <div>
      <Lead>
        {neighborhood ? (
          <>
            <b>{edges.length}</b> giao dịch trong bán kính <b>{String(p.hops ?? 1)}</b> bước quanh tài khoản.
          </>
        ) : (
          <>
            Hình dạng <b>{String(p.pattern ?? "—")}</b>
            {length !== null ? <> dài {length} chặng</> : null}
            {accounts.length ? <> qua {accounts.length} tài khoản</> : null}
            {hours !== null ? <>, hoàn tất trong {hours < 1 ? `${Math.round(hours * 60)} phút` : `${hours.toFixed(1)} giờ`}</> : null}.
          </>
        )}
      </Lead>
      <div className="max-h-44 overflow-auto">
        {edges.map((e, i) => (
          <div key={i} className="tabular flex items-center gap-2 border-b border-line/40 py-1 text-micro last:border-0">
            <span className="text-ink-mid">{String(e.from)}</span>
            <span className="text-ink-low">→</span>
            <span className="text-ink-mid">{String(e.to)}</span>
            <span className="ml-auto text-ink-low">GD {String(e.transaction_id)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Vì sao cảnh báo được xếp vào nhóm hành vi này. */
function TypologyMapping({ p }: { p: Payload }) {
  const a = (p.assignment ?? {}) as Payload;
  const required = (p.required_signals ?? []) as string[];
  const matched = (a.matched_required ?? []) as string[];
  return (
    <div>
      <Lead>
        Xếp vào nhóm <b>{String(p.typology_code ?? "—")} — {String(p.name ?? "")}</b>.{" "}
        {String(a.rationale ?? "")}
      </Lead>
      <Line label="Mô tả nhóm" value={String(p.description ?? "—")} />
      <Line label="Tín hiệu bắt buộc" value={required.length ? required.join(", ") : "—"} />
      <Line label="Tín hiệu đã khớp" value={matched.length ? matched.join(", ") : "—"} />
      {a.is_fallback === true && (
        <p className="mt-2 text-micro text-warn">
          Đây là nhóm mặc định: không tín hiệu nào đủ điều kiện, nên mã nhóm chưa được xác nhận.
        </p>
      )}
    </div>
  );
}

export function EvidenceBody({ type, payload }: { type: string; payload: unknown }) {
  const [showRaw, setShowRaw] = useState(false);
  const p = (payload ?? {}) as Payload;

  let body: React.ReactNode;
  switch (type) {
    case "RISK_BREAKDOWN":
      body = <RiskBreakdown p={p} />;
      break;
    case "RULE_TRIGGER":
      body = <RuleTrigger p={p} />;
      break;
    case "BEHAVIOR_FEATURE":
      body = <BehaviorFeature p={p} />;
      break;
    case "ANOMALY_EXPLANATION":
      body = <AnomalyExplanation p={p} />;
      break;
    case "TRANSACTION":
      body = <Transactions p={p} />;
      break;
    case "GRAPH_PATTERN":
      body = <GraphShape p={p} neighborhood={false} />;
      break;
    case "GRAPH_NEIGHBORHOOD":
      body = <GraphShape p={p} neighborhood />;
      break;
    case "TYPOLOGY_MAPPING":
      body = <TypologyMapping p={p} />;
      break;
    default:
      // Loại chưa có bộ hiển thị riêng vẫn phải xem được, chứ không biến mất.
      body = <Lead>Chưa có cách trình bày riêng cho loại bằng chứng này. Xem dữ liệu gốc bên dưới.</Lead>;
  }

  return (
    <div>
      {body}
      <button
        type="button"
        onClick={() => setShowRaw((v) => !v)}
        className="mt-3 text-micro text-ink-low underline decoration-dotted underline-offset-2 hover:text-ink-mid"
      >
        {showRaw ? "Ẩn dữ liệu gốc" : "Dữ liệu gốc (JSON)"}
      </button>
      {showRaw && (
        <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded bg-app p-2 text-micro text-ink-mid">
          {JSON.stringify(payload, null, 2)}
        </pre>
      )}
    </div>
  );
}
