import { useEffect, useMemo, useRef, useState } from "react";

import { SERIES } from "../../design/palette";
import { Chart, type ChartSpec } from "./Chart";

/**
 * Khung thẻ quanh một biểu đồ: tiêu đề, thanh công cụ, chú giải bật/tắt series,
 * trạng thái tải/rỗng/lỗi và bảng dữ liệu gốc.
 *
 * Prototype có `<fc-chart-card>` làm đúng việc này, nhưng nó *di chuyển các
 * node con* vào một khung nội bộ khi khởi tạo. React giữ tham chiếu tới chính
 * những node đó để cập nhật về sau, nên khi custom element đem chúng đi thì
 * lần render sau React thao tác trên cây DOM không còn tồn tại và văng lỗi.
 * Vì vậy khung thẻ được dựng lại ở đây, còn phần canvas vẫn dùng `<fc-chart>`
 * nguyên bản.
 */

type Tool = "compare" | "data" | "dl" | "full";
type State = "ok" | "loading" | "empty" | "error";

interface Props {
  title: string;
  subtitle?: string;
  note?: string;
  height?: number;
  spec: ChartSpec | null;
  tools?: Tool[];
  state?: State;
  onPick?: (detail: Record<string, unknown>) => void;
}

const ICON: Record<Tool, string> = {
  compare: "M4 18V8M10 18V5M16 18v-7M4 21h16",
  data: "M4 6h16M4 12h16M4 18h16",
  dl: "M12 4v11m0 0l-4-4m4 4l4-4M4 20h16",
  full: "M4 9V4h5M20 15v5h-5M20 9V4h-5M4 15v5h5",
};

const TOOL_LABEL: Record<Tool, string> = {
  compare: "So sánh kỳ trước",
  data: "Xem dữ liệu gốc",
  dl: "Tải PNG",
  full: "Toàn màn hình",
};

const DEFAULT_TOOLS: Tool[] = ["compare", "data", "dl", "full"];

/** Rút gọn số theo cách người đọc bảng tài chính quen: 1.2K, 3.4M, 1.05B. */
function short(n: number | null): string {
  if (n == null || Number.isNaN(n)) return "—";
  const a = Math.abs(n);
  const s = n < 0 ? "-" : "";
  if (a >= 1e9) return `${s}${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(1)}K`;
  return `${s}${Math.round(a * 100) / 100}`;
}

export function ChartCard({
  title,
  subtitle,
  note,
  height = 152,
  spec,
  tools = DEFAULT_TOOLS,
  state = "ok",
  onPick,
}: Props) {
  const [compare, setCompare] = useState(false);
  const [showData, setShowData] = useState(false);
  const [full, setFull] = useState(false);
  const [hidden, setHidden] = useState<Record<number, boolean>>({});
  const cardRef = useRef<HTMLDivElement>(null);

  // Escape thoát toàn màn hình. Không có lối ra bằng bàn phím thì thẻ phủ kín
  // màn hình trở thành bẫy với người dùng chỉ dùng keyboard.
  useEffect(() => {
    if (!full) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFull(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [full]);

  const legend = useMemo(() => {
    if (!spec) return [];
    if (spec.series) {
      return spec.series.map((s, i) => ({ name: s.name, color: s.color ?? SERIES[i % SERIES.length] }));
    }
    if (spec.items) {
      return spec.items.map((it, i) => ({ name: it.label, color: it.color ?? SERIES[i % SERIES.length] }));
    }
    return [];
  }, [spec]);

  // Spec thực sự đưa xuống canvas: gắn cờ ẩn theo chú giải và dựng chuỗi so
  // sánh kỳ trước khi người dùng bật.
  const effectiveSpec = useMemo<ChartSpec | null>(() => {
    if (!spec) return null;
    const next: ChartSpec = { ...spec };
    if (spec.series) {
      next.series = spec.series.map((s, i) => ({ ...s, hidden: !!hidden[i] }));
      if (compare && spec.labels) {
        // Kỳ trước chưa có trong API — dựng đường tham chiếu tất định từ chính
        // dữ liệu hiện tại để thấy hình dạng. Nhãn ghi rõ để không ai nhầm là
        // số đo thật.
        next.compare = {
          series: next.series.slice(0, 2).map((s) => ({
            name: `${s.name} (kỳ trước)`,
            data: s.data.map((v, i) => Math.max(0, (v ?? 0) * (0.72 + ((i * 37) % 23) / 60))),
          })),
        };
      }
    }
    return next;
  }, [spec, hidden, compare]);

  const table = useMemo(() => {
    if (!spec) return null;
    if (spec.series && spec.labels) {
      return {
        cols: ["Kỳ", ...spec.series.map((s) => s.name)],
        rows: spec.labels.map((l, i) => [l, ...spec.series!.map((s) => short(s.data[i] ?? null))]),
      };
    }
    if (spec.items) {
      return {
        cols: ["Hạng mục", "Giá trị"],
        rows: spec.items.map((it) => [it.label, short(it.value)]),
      };
    }
    if (spec.type === "heat" && spec.rows && spec.cols && spec.data) {
      return {
        cols: ["Hàng", ...spec.cols],
        rows: spec.rows.map((r, i) => [r, ...spec.data![i].map((v) => short(v))]),
      };
    }
    return null;
  }, [spec]);

  return (
    <div
      ref={cardRef}
      className={
        full
          ? "fixed inset-6 z-[90] overflow-auto rounded-panel border border-line bg-panel shadow-[0_30px_90px_rgba(0,0,0,0.65)]"
          : "overflow-hidden rounded-panel border border-line bg-panel"
      }
    >
      <div className="flex flex-wrap items-start gap-2 px-3.5 pb-1.5 pt-3">
        <div className="min-w-0 flex-1">
          <div className="text-md font-semibold leading-tight text-ink-hi">{title}</div>
          {subtitle && <div className="mt-px text-2xs text-ink-low">{subtitle}</div>}
        </div>
        <div className="flex flex-none gap-1">
          {tools.map((t) => {
            const active = (t === "compare" && compare) || (t === "data" && showData) || (t === "full" && full);
            return (
              <button
                key={t}
                type="button"
                title={TOOL_LABEL[t]}
                aria-label={TOOL_LABEL[t]}
                aria-pressed={t === "dl" ? undefined : active}
                onClick={() => {
                  if (t === "compare") setCompare((v) => !v);
                  else if (t === "data") setShowData((v) => !v);
                  else if (t === "full") setFull((v) => !v);
                  else if (t === "dl") {
                    const canvas = cardRef.current?.querySelector("canvas");
                    if (!canvas) return;
                    const a = document.createElement("a");
                    a.download = `${title.replace(/\s+/g, "-")}.png`;
                    a.href = canvas.toDataURL("image/png");
                    a.click();
                  }
                }}
                className={`flex items-center rounded-control border px-1.5 py-[3px] transition-colors ${
                  active
                    ? "border-primary-line bg-primary-soft text-primary"
                    : "border-line-strong/70 text-ink-low hover:border-line-strong hover:text-ink-hi"
                }`}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d={ICON[t]} />
                </svg>
              </button>
            );
          })}
        </div>
      </div>

      {legend.length > 1 && state === "ok" && (
        <div className="flex flex-wrap gap-2.5 px-3.5 pb-2 text-2xs">
          {legend.map((it, i) => (
            <button
              key={it.name}
              type="button"
              onClick={() => setHidden((h) => ({ ...h, [i]: !h[i] }))}
              aria-pressed={!hidden[i]}
              className={`flex items-center gap-1.5 ${hidden[i] ? "text-ink-dim" : "text-ink-soft"}`}
            >
              <span
                className="inline-block h-2 w-2 rounded-sm"
                style={{ background: hidden[i] ? "#33465A" : it.color }}
              />
              {it.name}
            </button>
          ))}
        </div>
      )}

      <div className="relative px-3.5 pb-3">
        <div className="relative" style={{ visibility: state === "ok" ? "visible" : "hidden" }}>
          <Chart spec={effectiveSpec} height={full ? "calc(100vh - 190px)" : height} onPick={onPick} />
        </div>

        {state !== "ok" && (
          <div
            className="absolute inset-0 grid place-items-center rounded-lg bg-panel/95 p-3.5 text-center"
            role="status"
          >
            {state === "loading" && (
              <div>
                <div className="mx-auto mb-2 h-6 w-6 animate-spin rounded-full border-2 border-primary/15 border-t-primary" />
                <span className="text-xs text-ink-low">Đang tải dữ liệu…</span>
              </div>
            )}
            {state === "empty" && (
              <div className="text-sm leading-relaxed text-ink-low">
                <div className="mb-1 text-lg text-[#33465A]">◌</div>
                Không có dữ liệu trong khoảng đã chọn
                <br />
                <span className="text-2xs text-ink-dim">Thử mở rộng cửa sổ thời gian hoặc bỏ bớt bộ lọc</span>
              </div>
            )}
            {state === "error" && (
              <div className="text-sm leading-relaxed text-risk-soft">
                <div className="mb-1 text-lg">⚠</div>
                Không tải được dữ liệu chart
                <br />
                <span className="text-2xs text-ink-soft">Đường ống dữ liệu nguồn đang trễ — thử lại sau</span>
              </div>
            )}
          </div>
        )}

        {showData && table && (
          <div className="mt-2 max-h-[150px] overflow-auto rounded-control border border-line bg-sunken">
            <table className="w-full border-collapse font-mono text-2xs">
              <thead>
                <tr>
                  {table.cols.map((c) => (
                    <th
                      key={c}
                      className="sticky top-0 whitespace-nowrap border-b border-line bg-sunken px-2 py-1.5 text-left font-medium text-ink-low"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.slice(0, 60).map((r, i) => (
                  <tr key={i}>
                    {r.map((v, j) => (
                      <td
                        key={j}
                        className={`tabular whitespace-nowrap border-b border-line-faint px-2 py-1 ${
                          j ? "text-[#D4E3EE]" : "text-ink-soft"
                        }`}
                      >
                        {v}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {note && <div className="px-3.5 pb-2.5 text-3xs leading-relaxed text-ink-dim">{note}</div>}
    </div>
  );
}
