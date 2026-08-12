import { Activity, TriangleAlert } from "lucide-react";

/**
 * Đường biểu diễn của thẻ xu hướng.
 *
 * Là hằng số viết tay, không phải dữ liệu tải về: màn đăng nhập nằm *trước*
 * xác thực nên không có quyền đọc bất kỳ số liệu thật nào. Vẽ một đường giả
 * rồi để người xem tưởng là số liệu vận hành thì đó là bịa, nên khối này luôn
 * đi kèm nhãn nói rõ nó là môi trường mô phỏng.
 */
const TREND = [18, 26, 22, 34, 30, 44, 39, 52, 46, 61, 55, 68, 63, 74, 82];

function Sparkline() {
  const w = 236;
  const h = 62;
  const max = Math.max(...TREND);
  const min = Math.min(...TREND);
  const points = TREND.map((v, i) => {
    const x = (i / (TREND.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * (h - 8) - 4;
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${w},${h} L0,${h} Z`;

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="overflow-visible">
      <defs>
        <linearGradient id="fc-login-spark" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#12D6C5" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#12D6C5" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill="url(#fc-login-spark)" />
      <path d={line} fill="none" stroke="#12D6C5" strokeWidth="1.6" strokeLinejoin="round" />
      {points.map(([x, y], i) =>
        i % 3 === 0 ? <circle key={i} cx={x} cy={y} r="2" fill="#5FE8DB" /> : null,
      )}
    </svg>
  );
}

/**
 * Cụm số liệu nổi ở góc dưới trái.
 *
 * Ba khối: một đường xu hướng, một điểm rủi ro, một bộ đếm cảnh báo. Tất cả
 * đều là số của môi trường mô phỏng và được ghi rõ như vậy ngay dưới.
 */
export function IntelligenceMetrics() {
  return (
    <div
      className="animate-up hidden max-w-2xl gap-2.5 xl:flex"
      style={{ animationDelay: "520ms", animationFillMode: "backwards" }}
    >
      <div className="flex-1 rounded-panel border border-line bg-side/55 p-3 backdrop-blur-[2px]">
        <div className="flex items-center justify-between">
          <span className="text-3xs uppercase tracking-[0.12em] text-ink-dim">Tín hiệu theo ngày</span>
          <Activity size={12} className="text-primary" aria-hidden />
        </div>
        <div className="mt-1.5">
          <Sparkline />
        </div>
      </div>

      <div className="w-[132px] rounded-panel border border-line bg-side/55 p-3 backdrop-blur-[2px]">
        <span className="text-3xs uppercase tracking-[0.12em] text-ink-dim">Điểm rủi ro</span>
        <div className="mt-1.5 flex items-baseline gap-1">
          <span className="tabular font-mono text-3xl font-semibold text-risk-soft">82</span>
          <span className="font-mono text-2xs text-ink-low">/100</span>
        </div>
        <span className="mt-1 inline-flex items-center gap-1 text-3xs text-risk-soft">
          <TriangleAlert size={10} aria-hidden />
          Rủi ro cao
        </span>
      </div>

      <div className="w-[132px] rounded-panel border border-line bg-side/55 p-3 backdrop-blur-[2px]">
        <span className="text-3xs uppercase tracking-[0.12em] text-ink-dim">Đang theo dõi</span>
        <div className="mt-1.5 tabular font-mono text-3xl font-semibold text-primary">39</div>
        <span className="mt-1 block text-3xs text-ink-low">cảnh báo đang mở</span>
      </div>
    </div>
  );
}
