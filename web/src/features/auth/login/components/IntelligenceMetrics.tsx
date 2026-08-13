import { C } from "../../../../design/palette";

/**
 * Đường biểu diễn của dải số liệu.
 *
 * Là hằng số viết tay, không phải dữ liệu tải về: màn đăng nhập nằm *trước* xác
 * thực nên không có quyền đọc bất kỳ số liệu thật nào. Vẽ một đường giả rồi để
 * người xem tưởng là số liệu vận hành thì đó là bịa, nên dải này luôn đi kèm
 * nhãn ở chân trang nói rõ nó là môi trường mô phỏng.
 */
const TREND = [18, 26, 22, 34, 30, 44, 39, 52, 46, 61, 55, 68, 63, 74, 82];

function Sparkline() {
  const w = 128;
  const h = 30;
  const max = Math.max(...TREND);
  const min = Math.min(...TREND);
  const points = TREND.map((v, i) => {
    const x = (i / (TREND.length - 1)) * w;
    const y = h - ((v - min) / (max - min || 1)) * (h - 6) - 3;
    return [x, y] as const;
  });
  const line = points.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");

  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} aria-hidden className="mt-1.5 block">
      <path d={line} fill="none" stroke={C.info} strokeWidth="1.4" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={points[points.length - 1][0]} cy={points[points.length - 1][1]} r="2.2" fill={C.info} />
    </svg>
  );
}

const METRICS = [
  { label: "Điểm rủi ro", value: "82", unit: "/100", tone: "text-warn" },
  { label: "Đang theo dõi", value: "39", unit: "cảnh báo mở", tone: "text-ink-hi" },
] as const;

/**
 * Dải số liệu cuối cột trái.
 *
 * Một dải ngang, không phải ba thẻ có viền. Bản cũ đặt cụm này rơi xuống tận
 * đáy màn hình, cách hero hơn 250px, nên nó trông như thuộc về một phần khác
 * của trang; ở đây nó nằm ngay dưới dải năng lực và cùng một nhịp dọc.
 */
export function IntelligenceMetrics() {
  return (
    <div
      className="animate-up mt-7 hidden flex-wrap items-end gap-x-10 gap-y-5 border-t border-line-faint pt-6 sm:flex"
      style={{ animationDelay: "440ms", animationFillMode: "backwards" }}
    >
      <div className="min-w-0">
        <div className="fc-eyebrow">Tín hiệu theo ngày</div>
        <Sparkline />
      </div>

      {METRICS.map(({ label, value, unit, tone }) => (
        <div key={label} className="min-w-0">
          <div className="fc-eyebrow">{label}</div>
          <div className="mt-1 flex items-baseline gap-1.5">
            <span className={`tabular font-mono text-4xl font-semibold ${tone}`}>{value}</span>
            <span className="text-2xs text-ink-low">{unit}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
