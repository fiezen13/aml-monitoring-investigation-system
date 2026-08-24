import { useState, type ReactNode } from "react";

import { api } from "../api/client";
import type { FcBitcoinExplanation, FcBitcoinRow } from "../api/client";
import { int } from "../api/fcFormat";
import { useApi } from "../api/useApi";
import { ErrorState, PageShell } from "../components/ui";
import { Chip, Empty, KpiCard, Panel, ProgressBar, ScreenTitle, Skeleton } from "../components/fc/primitives";
import { C } from "../design/palette";
import { businessReasons, reviewSuggestions } from "./crypto/businessLanguage";
import { useRbac } from "../rbac/useRbac";
import { PERMISSIONS } from "../rbac/permissions";

/**
 * Truy vết tài sản mã hoá — nhánh Bitcoin (Elliptic gốc + ngữ nghĩa DFRWS 2026).
 *
 * Kiến trúc thông tin bám nghiệp vụ AML: mỗi giao dịch mở ra một hồ sơ có thứ
 * bậc — [A] tóm tắt · [B] vì sao bị gắn cờ · [C] bằng chứng đồ thị · [D] giải
 * thích mô hình (SHAP thu gọn) · [E] giới hạn · [F] cần kiểm tra tiếp. Nguyên
 * tắc: (1) KHÔNG bịa nghĩa đặc trưng ẩn danh; (2) SHAP là "phần giải thích của
 * model", KHÔNG phải "phần trăm nguyên nhân"; (3) ĐIỂM RỦI RO tách khỏi CHẤT
 * LƯỢNG GIẢI THÍCH; (4) láng giềng ĐÃ BIẾT bất hợp pháp (ground truth) khác hẳn
 * láng giềng MODEL DỰ ĐOÁN. Mọi con số đọc từ `bitcoin_scored_tx` (chấm sẵn).
 */

const LEVEL_META: Record<string, { label: string; color: string }> = {
  CRITICAL: { label: "Rất cao", color: C.risk },
  HIGH: { label: "Cao", color: C.warn },
  MEDIUM: { label: "Trung bình", color: C.info },
  LOW: { label: "Thấp", color: C.inkSoft },
};

const VIEWS = [
  ["flagged", "Model gắn cờ nghi ngờ"],
  ["review", "Cần rà soát (cao/rất cao)"],
  ["all", "Toàn bộ tập test"],
] as const;

/** `0.9846` → `98,5%`. Dùng cho các tỉ lệ đã ký của release. */
function rate(value: number | null): string {
  return value == null ? "—" : `${(value * 100).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}%`;
}

/** Số gọn cho giá trị đặc trưng đọc được (số nguyên bỏ phần thập phân thừa). */
function fmtVal(v: number): string {
  if (Math.abs(v - Math.round(v)) < 1e-9) return String(Math.round(v));
  return v.toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
}

/** Nhãn nhỏ in hoa cho tiêu đề mục. */
function SectionLabel({ children }: { children: ReactNode }) {
  return <div className="text-3xs font-semibold uppercase tracking-wider text-ink-low">{children}</div>;
}

/** Trạng thái một nút láng giềng: ưu tiên ground-truth trước dự đoán. */
function neighbourKind(n: FcBitcoinRow["graph_neighbours"][number]): "known" | "predicted" | "licit" | "unknown" {
  if (n.known_illicit) return "known";
  if (n.flag === true) return "predicted";
  if (n.flag === false) return "licit";
  return "unknown";
}

// Nhãn trạng thái nút theo ngôn ngữ NGHIỆP VỤ (§15) — không dùng nhãn dataset/ML.
// Phân biệt ground-truth vs dự đoán là thông tin nghiên cứu → để ở phần kỹ thuật.
const NODE_STYLE: Record<string, { color: string; label: string }> = {
  known: { color: C.risk, label: "Đã có cảnh báo" },
  predicted: { color: C.warn, label: "Nghi ngờ rủi ro" },
  licit: { color: C.inkSoft, label: "Chưa có cảnh báo" },
  unknown: { color: C.line, label: "Chưa đủ thông tin" },
};

/**
 * [C] Đồ thị lân cận 1 chặng: THƯỢNG NGUỒN → GIAO DỊCH NÀY → HẠ NGUỒN.
 *
 * Nút giữa nổi bật (viền + nhãn). Màu/hình phân biệt ĐÃ BIẾT bất hợp pháp (đỏ)
 * với MODEL DỰ ĐOÁN (cam) — hai trạng thái không được nhìn giống nhau. Đây là
 * NGỮ CẢNH điều tra, không phải thứ Random Forest dùng để chấm.
 */
function NetworkGraph({ row }: { row: FcBitcoinRow }) {
  const W = 300;
  const H = 176;
  const cx = W / 2;
  const cy = H / 2;
  const centerColor = LEVEL_META[row.risk_level]?.color ?? C.risk;

  const ins = row.graph_neighbours.filter((n) => n.dir === "in" || n.dir === "both").slice(0, 6);
  const outs = row.graph_neighbours.filter((n) => n.dir === "out").slice(0, 6);
  const place = (list: FcBitcoinRow["graph_neighbours"], x: number) =>
    list.map((n, i) => ({ n, x, y: list.length === 1 ? cy : 26 + ((H - 52) * i) / (list.length - 1) }));
  const left = place(ins, 42);
  const right = place(outs, W - 42);
  const moreIn = Math.max(0, (row.graph_in_degree ?? 0) - ins.length);
  const moreOut = Math.max(0, (row.graph_out_degree ?? 0) - outs.length);

  return (
    <div>
      <div className="flex justify-between px-1 text-3xs uppercase tracking-wide text-ink-low">
        <span>Tiền đến từ ({int(row.graph_in_degree ?? 0)})</span>
        <span>Tiền chuyển tới ({int(row.graph_out_degree ?? 0)})</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Đồ thị lân cận giao dịch">
        {left.map(({ x, y }, i) => (
          <line key={`li${i}`} x1={x} y1={y} x2={cx - 12} y2={cy} stroke={C.line} strokeWidth={1} markerEnd="url(#arr)" />
        ))}
        {right.map(({ x, y }, i) => (
          <line key={`lo${i}`} x1={cx + 12} y1={cy} x2={x} y2={y} stroke={C.line} strokeWidth={1} markerEnd="url(#arr)" />
        ))}
        <defs>
          <marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 Z" fill={C.inkDim} />
          </marker>
        </defs>
        {[...left, ...right].map(({ n, x, y }, i) => {
          const kind = neighbourKind(n);
          return (
            <circle
              key={`n${i}`}
              cx={x}
              cy={y}
              r={kind === "known" ? 7 : 6}
              fill={NODE_STYLE[kind].color}
              opacity={kind === "unknown" ? 0.5 : 1}
              stroke={kind === "known" ? C.risk : "none"}
              strokeWidth={kind === "known" ? 3 : 0}
              strokeOpacity={0.35}
            />
          );
        })}
        {/* Nút giữa = giao dịch đang xem, có nhãn. */}
        <circle cx={cx} cy={cy} r={11} fill={centerColor} />
        <circle cx={cx} cy={cy} r={11} fill="none" stroke={centerColor} strokeWidth={4} opacity={0.3} />
        <text x={cx} y={cy + 24} fill={C.inkMid} fontSize={8} fontWeight={600} textAnchor="middle">
          GIAO DỊCH NÀY
        </text>
        {moreIn > 0 && (
          <text x={42} y={H - 6} fill={C.inkLow} fontSize={8} textAnchor="middle">
            +{moreIn} nữa
          </text>
        )}
        {moreOut > 0 && (
          <text x={W - 42} y={H - 6} fill={C.inkLow} fontSize={8} textAnchor="middle">
            +{moreOut} nữa
          </text>
        )}
      </svg>
      {/* Chú giải: không chỉ dựa vào màu — kèm nhãn chữ. */}
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {(["known", "predicted", "licit", "unknown"] as const).map((k) => (
          <span key={k} className="flex items-center gap-1 text-3xs text-ink-low">
            <span className="h-2 w-2 flex-none rounded-full" style={{ background: NODE_STYLE[k].color }} />
            {NODE_STYLE[k].label}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * [D] Giải thích mô hình — SHAP kỹ thuật, THU GỌN mặc định.
 *
 * Chỉ mở khi chuyên viên bấm "Xem chi tiết kỹ thuật". Đặc trưng ẩn danh KHÔNG
 * đặt tên. Thanh đỏ = đẩy điểm lên, xanh = kéo xuống — đây là đóng góp vào DỰ
 * ĐOÁN của model, không phải nguyên nhân phạm tội.
 */
function TechnicalShap({ row }: { row: FcBitcoinRow }) {
  const [open, setOpen] = useState(false);
  if (!row.drivers.length) return null;
  const maxAbs = Math.max(...row.drivers.map((d) => Math.abs(d.contribution)), 1e-9);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="text-2xs text-primary hover:underline"
      >
        {open ? "Ẩn chi tiết kỹ thuật SHAP" : "Xem chi tiết kỹ thuật SHAP (đóng góp từng đặc trưng)"}
      </button>
      {open && (
        <div className="mt-1.5 rounded-panel border border-line-faint bg-sunken/40 p-2.5">
          <div className="flex flex-col gap-1">
            {row.drivers.map((d, i) => {
              const w = Math.max(6, (Math.abs(d.contribution) / maxAbs) * 100);
              const pushes = d.contribution >= 0;
              return (
                <div key={i} className="grid items-center gap-2" style={{ gridTemplateColumns: "1fr 118px" }}>
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="h-1.5 flex-none rounded-full" style={{ width: `${w}%`, maxWidth: 160, background: pushes ? C.risk : C.ok }} />
                    <span className={`truncate text-2xs ${d.meaningful ? "text-ink-hi" : "font-mono italic text-ink-low"}`}>
                      {d.meaningful ? d.label : d.name}
                    </span>
                  </div>
                  <span className="tabular text-right font-mono text-3xs text-ink-soft">
                    SHAP {d.contribution >= 0 ? "+" : ""}
                    {d.contribution.toFixed(3)}
                    {d.meaningful ? ` · =${fmtVal(d.value)}` : ""}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="mt-1.5 text-3xs leading-relaxed text-ink-low">
            SHAP đo mỗi đặc trưng làm tăng/giảm DỰ ĐOÁN của model bao nhiêu — không phải phần trăm xác suất phạm
            tội. Đặc trưng ẩn danh (feature_N) không có nghĩa công bố nên không được diễn giải thành hành vi.
          </p>
        </div>
      )}
    </div>
  );
}

/** Giải thích Gemini ON-DEMAND — chỉ gọi khi bấm (không precompute 67k lệnh LLM). */
function AiExplainPanel({ txId }: { txId: string }) {
  const [state, setState] = useState<{ loading: boolean; data?: FcBitcoinExplanation; error?: string }>({ loading: false });
  const run = async () => {
    setState({ loading: true });
    try {
      setState({ loading: false, data: await api.explainBitcoin(txId) });
    } catch (e) {
      setState({ loading: false, error: e instanceof Error ? e.message : "Lỗi gọi agent" });
    }
  };
  return (
    <div className="rounded-panel border border-line-faint bg-sunken/40 p-2.5">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel>Giải thích của AI Agent</SectionLabel>
        <button
          type="button"
          onClick={run}
          disabled={state.loading}
          className="rounded-control border border-primary-line bg-primary-soft px-2.5 py-1 text-2xs font-medium text-primary disabled:opacity-50"
        >
          {state.loading ? "Đang gọi AI Agent…" : state.data ? "Chạy lại" : "AI giải thích"}
        </button>
      </div>
      {state.error && <p className="mt-1 text-2xs" style={{ color: C.risk }}>{state.error}</p>}
      {!state.data && !state.loading && !state.error && (
        <p className="mt-1 text-2xs text-ink-low">Gọi AI Agent diễn đạt bằng chứng đã chấm sang tiếng Việt (on-demand). Agent không thay điểm model.</p>
      )}
      {state.data && (
        <div className="mt-1.5 flex flex-col gap-1.5">
          <p className="text-xs leading-relaxed text-ink-hi">{state.data.summary}</p>
          {state.data.key_reasons.length > 0 && (
            <ul className="flex flex-col gap-0.5">
              {state.data.key_reasons.map((r, i) => (
                <li key={i} className="text-2xs leading-relaxed text-ink-soft">• {r}</li>
              ))}
            </ul>
          )}
          {state.data.next_steps.length > 0 && (
            <div>
              <div className="text-3xs uppercase tracking-wide text-ink-low">Bước tiếp</div>
              <ol className="mt-0.5 flex flex-col gap-0.5">
                {state.data.next_steps.map((s, i) => (
                  <li key={i} className="text-2xs leading-relaxed text-ink-soft">{i + 1}. {s}</li>
                ))}
              </ol>
            </div>
          )}
          <p className="text-2xs italic leading-relaxed text-ink-low">{state.data.caveat}</p>
        </div>
      )}
    </div>
  );
}

/** Một hồ sơ giao dịch: mở rộng ra 6 mục A–F. */
/** [ẨN MẶC ĐỊNH] Chi tiết kỹ thuật & kiểm toán mô hình — chỉ Quản trị hệ thống. */
function TechnicalPanel({ row }: { row: FcBitcoinRow }) {
  const [open, setOpen] = useState(false);
  const rbac = useRbac();
  // Nhãn tham chiếu (dataset) chỉ hiện cho vai trò giám sát mô hình — chống thiên
  // kiến xác nhận cho chuyên viên (§25-28). Analyst KHÔNG có VIEW_MODEL_QUALITY.
  const canSeeLabel = rbac.can(PERMISSIONS.VIEW_MODEL_QUALITY);
  const interp = row.interpretable_ratio ?? 0;
  const ge = row.graph_evidence ?? {};
  const gt = ge.ground_truth_exposure;
  return (
    <div className="rounded-panel border border-line-faint bg-sunken/30 p-2.5">
      <button type="button" onClick={() => setOpen((o) => !o)} className="w-full text-left text-2xs font-medium text-ink-soft">
        {open ? "▾" : "▸"} Chi tiết kỹ thuật &amp; kiểm toán mô hình
      </button>
      {open && (
        <div className="mt-2 flex flex-col gap-2 text-2xs">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            {[
              ["Điểm mô hình P(illicit)", row.illicit_prob.toFixed(3)],
              ["Mức rủi ro", row.risk_level],
              ["Thuật toán", "Random Forest · Elliptic (gốc)"],
              ["Chất lượng giải thích", `${row.explanation_quality ?? "—"} · ${Math.round(interp * 100)}% đọc được`],
              ["Sức mạnh bằng chứng đồ thị", row.evidence_strength ?? "—"],
              ["Hop gần nhất tới illicit đã biết", gt?.nearest_known_illicit_hop ?? "—"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-line-faint/60 py-0.5">
                <span className="text-ink-low">{k}</span>
                <span className="tabular font-mono text-ink-hi">{v}</span>
              </div>
            ))}
          </div>
          {canSeeLabel && (
            <div className="rounded-control border border-line-faint bg-elev/40 p-2">
              <span className="text-3xs uppercase tracking-wide text-ink-low">Nhãn tham chiếu (chỉ tập nghiên cứu Elliptic — dùng để kiểm định mô hình)</span>
              <div className="mt-0.5 font-medium text-ink-hi">
                {row.true_label ? (row.true_label === "illicit" ? "illicit" : "licit") : "không có nhãn"}
              </div>
            </div>
          )}
          {/* Đóng góp đặc trưng (SHAP) — chỉ trong kỹ thuật. */}
          <TechnicalShap row={row} />
          <p className="text-3xs leading-relaxed text-ink-low">
            Ngữ nghĩa đặc trưng phục hồi theo DFRWS 2026 (151/166). Giá trị đã chuẩn hoá (z-score); SHAP là đóng góp
            vào dự đoán, KHÔNG phải % xác suất/nguyên nhân. Đây là tái lập benchmark Elliptic — có giới hạn leakage
            (không phải hiệu năng tổng quát thực tế).
          </p>
        </div>
      )}
    </div>
  );
}

/** Hồ sơ giao dịch — GÓC NHÌN CHUYÊN VIÊN AML (không thuật ngữ ML ở mặc định). */
function TxDetail({ row }: { row: FcBitcoinRow }) {
  const level = LEVEL_META[row.risk_level] ?? LEVEL_META.LOW;
  const reasons = businessReasons(row.drivers);
  const inCount = row.graph_in_degree ?? 0;
  const outCount = row.graph_out_degree ?? 0;
  const flaggedRelated = row.graph_flagged_neighbours ?? 0; // model gắn cờ (KHÔNG dùng nhãn dataset)
  const IMPACT_COLOR: Record<string, string> = { CAO: C.risk, "TRUNG BÌNH": C.warn, THẤP: C.info };
  const support: Array<[boolean, string]> = [
    [reasons.length > 0, "Có nhiều dấu hiệu bất thường từ hành vi giao dịch"],
    [flaggedRelated > 0, "Có giao dịch liên quan cũng đang được hệ thống cảnh báo"],
    [false, "Chưa có thông tin định danh chủ thể"],
    [false, "Chưa có dữ liệu đối chiếu danh sách cấm / vùng rủi ro"],
    [false, "Chưa có thông tin từ nguồn tình báo blockchain bên ngoài"],
  ];

  return (
    <div className="mt-2 flex flex-col gap-3">
      {/* HEADER nghiệp vụ: ưu tiên rà soát + trạng thái (không MODEL RISK). */}
      <div className="grid gap-2 rounded-panel border border-line-faint bg-elev/40 p-3 sm:grid-cols-2">
        <div>
          <SectionLabel>Mức độ ưu tiên rà soát</SectionLabel>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span className="text-xl font-semibold" style={{ color: level.color }}>{level.label}</span>
            <span className="tabular font-mono text-sm text-ink-soft">{Math.round(row.illicit_prob * 100)}/100</span>
          </div>
        </div>
        <div className="sm:border-l sm:border-line-faint sm:pl-3">
          <SectionLabel>Trạng thái</SectionLabel>
          <div className="mt-0.5 text-xl font-semibold text-ink-hi">Chưa rà soát</div>
        </div>
      </div>

      {/* DẤU HIỆU ĐÁNG CHÚ Ý — ngôn ngữ nghiệp vụ, không SHAP/percentile/feature. */}
      <div>
        <SectionLabel>Dấu hiệu đáng chú ý</SectionLabel>
        <div className="mt-1 flex flex-col gap-1.5">
          {reasons.length === 0 ? (
            <p className="text-2xs text-ink-soft">Chưa trích được dấu hiệu diễn giải rõ; xem phần kỹ thuật bên dưới.</p>
          ) : (
            reasons.map((r, i) => (
              <div key={i} className="rounded-panel border border-line-faint bg-sunken/40 p-2.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="grid h-4 w-4 flex-none place-items-center rounded-full bg-elev text-3xs font-semibold text-ink-mid">{i + 1}</span>
                    <span className="text-xs font-medium text-ink-hi">{r.title}</span>
                  </div>
                  <span className="flex-none rounded-control px-1.5 py-0.5 text-3xs font-semibold uppercase"
                    style={{ color: IMPACT_COLOR[r.impact], background: `${IMPACT_COLOR[r.impact]}1a` }}>
                    Ảnh hưởng: {r.impact}
                  </span>
                </div>
                <p className="mt-1 text-2xs leading-relaxed text-ink-soft">{r.description}</p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* DÒNG TIỀN LIÊN QUAN — trước → giao dịch này → sau. */}
      <div className="rounded-panel border border-line-faint bg-sunken/40 p-2.5">
        <SectionLabel>Dòng tiền liên quan</SectionLabel>
        <div className="mt-1.5 flex flex-col items-center gap-1 text-xs text-ink-soft">
          <span><b className="text-ink-hi">{int(inCount)}</b> giao dịch trước (nơi tiền đến từ đó)</span>
          <span className="text-ink-low">↓</span>
          <span className="rounded-control px-3 py-1 font-medium" style={{ color: level.color, background: `${level.color}1a` }}>GIAO DỊCH ĐANG RÀ SOÁT</span>
          <span className="text-ink-low">↓</span>
          <span><b className="text-ink-hi">{int(outCount)}</b> giao dịch tiếp theo (nơi tiền được chuyển tới)</span>
        </div>
        <div className="mt-2 flex justify-center">
          <div className="w-full max-w-[320px]"><NetworkGraph row={row} /></div>
        </div>
      </div>

      {/* THÔNG TIN HỖ TRỢ RÀ SOÁT — chỉ hiện cái backend thực sự biết. */}
      <div className="rounded-panel border border-line-faint bg-sunken/40 p-2.5">
        <SectionLabel>Thông tin hỗ trợ rà soát</SectionLabel>
        <ul className="mt-1 flex flex-col gap-0.5 text-2xs leading-relaxed">
          {support.map(([ok, txt], i) => (
            <li key={i} style={{ color: ok ? C.inkSoft : C.inkLow }}>
              <span style={{ color: ok ? C.ok : C.inkDim }}>{ok ? "✓" : "○"}</span> {txt}
            </li>
          ))}
        </ul>
      </div>

      {/* ĐỀ XUẤT RÀ SOÁT — sinh từ bằng chứng thật, ngôn ngữ nghiệp vụ. */}
      <div className="rounded-panel border border-line-faint bg-sunken/40 p-2.5">
        <SectionLabel>Đề xuất rà soát</SectionLabel>
        <ol className="mt-1 flex flex-col gap-0.5 text-2xs leading-relaxed text-ink-soft">
          {reviewSuggestions(inCount, outCount, flaggedRelated).map((s, i) => (
            <li key={i}>{i + 1}. {s}</li>
          ))}
        </ol>
      </div>

      {/* Trợ lý AI — tóm tắt ngắn bằng tiếng Việt nghiệp vụ (on-demand). */}
      <AiExplainPanel txId={row.tx_id} />

      {/* Kỹ thuật & nhãn tham chiếu — ẩn mặc định, không cho analyst mặc định. */}
      <TechnicalPanel row={row} />
    </div>
  );
}

/** Hàng trong hàng đợi — gọn, ngôn ngữ nghiệp vụ (không nhãn dataset, không ML). */
function QueueRow({ row }: { row: FcBitcoinRow }) {
  const [open, setOpen] = useState(false);
  const level = LEVEL_META[row.risk_level] ?? LEVEL_META.LOW;
  const score = Math.round(row.illicit_prob * 100);

  return (
    <div className="px-3.5 py-3">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex w-full flex-wrap items-center gap-2.5 text-left">
        <span className="tabular font-mono text-2xl font-semibold tabular-nums" style={{ color: level.color }}>{score}</span>
        <span className="text-2xs text-ink-low">/100 · ưu tiên</span>
        <Chip color={level.color}>{level.label}</Chip>
        <span className="rounded-control px-1.5 py-0.5 text-3xs font-medium text-ink-soft" style={{ background: `${C.inkSoft}14` }}>
          Chưa rà soát
        </span>
        <span className="font-mono text-2xs text-ink-low" title={row.tx_id}>mã {row.tx_id}</span>
        <span className="ml-auto text-2xs text-primary">{open ? "Thu gọn ▲" : "Xem hồ sơ ▼"}</span>
      </button>

      {!open && (
        <p className="mt-1.5 text-sm leading-relaxed text-ink-hi">
          Giao dịch được xếp mức ưu tiên rà soát <b style={{ color: level.color }}>{level.label.toLowerCase()}</b> do nhiều dấu hiệu bất thường từ hành vi giao dịch.
        </p>
      )}
      {open && <TxDetail row={row} />}
    </div>
  );
}

export function CryptoPage() {
  const [view, setView] = useState<string>("flagged");
  const [page, setPage] = useState(1);
  const pageSize = 50;
  const data = useApi(
    () => api.bitcoin({ view, page, page_size: pageSize }),
    [view, page],
    `bitcoin:${view}:${page}`,
  );

  const summary = data.data?.summary;
  const rows = data.data?.rows ?? [];
  const total = data.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const empty = summary && summary.total_scored === 0;
  // Chỉ số kiểm định mô hình (precision/nhãn thật) chỉ cho vai trò giám sát mô hình.
  const showBenchmark = useRbac().can(PERMISSIONS.VIEW_MODEL_QUALITY);

  return (
    <PageShell variant="dense">
      <ScreenTitle
        title="Truy vết tài sản mã hoá — nhánh Bitcoin"
        meta="Giám sát giao dịch Bitcoin nghi ngờ. Hệ thống xếp mức ưu tiên rà soát dựa trên hành vi giao dịch — đây là tín hiệu để ưu tiên điều tra, không phải kết luận."
      />

      {data.error && <ErrorState detail={data.error} onRetry={data.reload} />}

      {empty ? (
        <Empty
          text="Chưa nạp điểm nhánh Bitcoin"
          hint="Chạy: .venv/bin/python -m scripts.build_elliptic_scored (chấm tập test Elliptic gốc và nạp vào DB)."
        />
      ) : (
        <>
          <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))" }}>
            {data.loading && !summary ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-[76px] animate-pulse rounded-panel bg-panel" />
              ))
            ) : (
              <>
                <KpiCard
                  label="Giao dịch đã phân tích"
                  value={int(summary?.total_scored ?? 0)}
                  valueColor={C.inkHi}
                  delta="trong kỳ giám sát"
                />
                <KpiCard
                  label="Cần rà soát"
                  value={int(summary?.requires_review ?? 0)}
                  valueColor={C.risk}
                  delta={`${int(summary?.flagged_illicit ?? 0)} giao dịch được gắn cờ`}
                />
                {showBenchmark && (
                  <>
                    <KpiCard
                      label="Gắn cờ đúng (kiểm định mô hình)"
                      value={rate(summary?.precision ?? null)}
                      valueColor={C.ok}
                      delta={`bắt được ${rate(summary?.recall ?? null)} số ca thật`}
                    />
                    <KpiCard
                      label="Ca bất hợp pháp thật trong tập"
                      value={int(summary?.illicit_true_total ?? 0)}
                      valueColor={C.warn}
                      delta={`model bắt trúng ${int(summary?.flagged_true_positive ?? 0)}`}
                    />
                  </>
                )}
              </>
            )}
          </div>

          {summary && (
            <Panel title="Phân bố mức nghi ngờ" subtitle="Trên toàn bộ tập test đã chấm">
              <div className="flex flex-col gap-2">
                {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((lvl) => {
                  const count = summary.by_level[lvl] ?? 0;
                  const meta = LEVEL_META[lvl];
                  const width = summary.total_scored ? (count / summary.total_scored) * 100 : 0;
                  return (
                    <div key={lvl} className="grid items-center gap-2" style={{ gridTemplateColumns: "84px 1fr 70px" }}>
                      <Chip color={meta.color}>{meta.label}</Chip>
                      <ProgressBar value={width} color={meta.color} />
                      <span className="tabular text-right font-mono text-xs text-ink-soft">{int(count)}</span>
                    </div>
                  );
                })}
              </div>
            </Panel>
          )}

          <div className="flex flex-wrap gap-1.5">
            {VIEWS.map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setView(key);
                  setPage(1);
                }}
                className={`rounded-control border px-3 py-1.5 text-base transition-colors ${
                  view === key
                    ? "border-primary-line bg-primary-soft text-primary"
                    : "border-line-strong/70 text-ink-soft hover:text-ink-hi"
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <Panel bodyClassName="px-0">
            <div className="flex items-center justify-between px-3.5 pb-2 text-2xs text-ink-low">
              <span>{int(total)} giao dịch khớp bộ lọc</span>
              <span>
                trang {page}/{pageCount}
              </span>
            </div>

            {data.loading && <Skeleton rows={8} />}
            {!data.loading && !rows.length && <Empty text="Không có giao dịch nào khớp bộ lọc này" />}

            <div className="flex flex-col divide-y divide-line-faint">
              {rows.map((r) => (
                <QueueRow key={r.tx_id} row={r} />
              ))}
            </div>

            {pageCount > 1 && (
              <div className="flex items-center justify-center gap-2 px-3.5 pt-3">
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded-control border border-line-strong px-3 py-1 text-xs text-ink-soft disabled:opacity-40"
                >
                  Trước
                </button>
                <span className="text-2xs text-ink-low">
                  {page}/{pageCount}
                </span>
                <button
                  type="button"
                  disabled={page >= pageCount}
                  onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  className="rounded-control border border-line-strong px-3 py-1 text-xs text-ink-soft disabled:opacity-40"
                >
                  Sau
                </button>
              </div>
            )}
          </Panel>

          <Panel title="Giới hạn của phương pháp" subtitle="Phải công bố cùng mọi kết quả nhánh Bitcoin">
            <p className="text-xs leading-relaxed text-ink-soft">
              Kết quả là <b className="text-ink-mid">tín hiệu thống kê để ưu tiên rà soát</b>, không phải kết luận. Hệ
              thống mô tả các dấu hiệu bất thường bằng ngôn ngữ nghiệp vụ; chi tiết kỹ thuật và cơ sở đánh giá của mô
              hình nằm trong phần "Chi tiết kỹ thuật" ở mỗi giao dịch (mặc định ẩn).
            </p>
            <p className="mt-2 text-xs leading-relaxed text-ink-low">
              Kết quả dùng để <b className="text-ink-mid">ưu tiên rà soát</b>, không khẳng định giao dịch là vi phạm hay
              rửa tiền. Các dấu hiệu là <b className="text-ink-mid">quan sát</b> từ hành vi giao dịch, cần chuyên viên
              rà soát độc lập trước khi kết luận. Cơ sở đánh giá kỹ thuật của mô hình nằm trong phần "Chi tiết kỹ thuật"
              ở mỗi giao dịch.
            </p>
          </Panel>
        </>
      )}
    </PageShell>
  );
}
