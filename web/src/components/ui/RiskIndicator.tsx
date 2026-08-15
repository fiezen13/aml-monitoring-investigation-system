import { getRiskColor, getRiskLabel, getRiskTone } from "../../design/risk";
import { NUMERIC } from "../../design/typography";
import { Badge } from "./Badge";

/**
 * Hiển thị điểm rủi ro 0–100.
 *
 * Ba dáng cho ba ngữ cảnh, nhưng **một thang duy nhất** — xem `design/risk.ts`
 * để biết vì sao điều đó lại là một sửa lỗi chứ không phải một lựa chọn thẩm mỹ.
 *
 *   bar   — bảng dài: thanh dài theo điểm, đọc được khi liếc qua hàng chục dòng
 *   badge — ô số nền tint, dùng khi cột hẹp
 *   dot   — chỉ một chấm màu, dùng trong danh sách rất dày và trong HUD
 */

interface Props {
  score: number;
  variant?: "bar" | "badge" | "dot";
  /** Bề rộng tối đa của thanh, chỉ có nghĩa với `variant="bar"`. */
  width?: number;
  /** Kèm nhãn chữ ("Nghiêm trọng"). Bảng dày thường tắt để đỡ chật. */
  showLabel?: boolean;
  className?: string;
}

export function RiskIndicator({
  score,
  variant = "bar",
  width = 44,
  showLabel = false,
  className = "",
}: Props) {
  const rounded = Math.round(score);
  const color = getRiskColor(rounded);
  const tone = getRiskTone(rounded);
  const label = getRiskLabel(rounded);
  const title = `${label} — điểm ${rounded}/100. Điểm luôn phải xem kèm yếu tố đóng góp (NT7).`;

  if (variant === "badge") {
    return (
      <Badge tone={tone} icon={false} title={title} className={`${NUMERIC} min-w-[30px] justify-center ${className}`}>
        {rounded}
        {showLabel && <span className="ml-1 font-sans font-normal">{label}</span>}
      </Badge>
    );
  }

  if (variant === "dot") {
    return (
      <span title={title} className={`inline-flex items-center gap-1.5 ${className}`}>
        <span className="h-2 w-2 flex-none rounded-full" style={{ background: color }} aria-hidden />
        <b className={`${NUMERIC} text-data`} style={{ color }}>
          {rounded}
        </b>
        {showLabel && <span className="text-meta text-ink-low">{label}</span>}
      </span>
    );
  }

  const pct = `${Math.max(0, Math.min(100, rounded))}%`;
  return (
    <span title={title} className={`flex items-center gap-1.5 ${className}`}>
      <span
        className="h-1 flex-1 rounded-sm"
        style={{
          maxWidth: width,
          background: `linear-gradient(90deg, ${color} ${pct}, var(--line-base) ${pct})`,
        }}
        aria-hidden
      />
      <b className={`${NUMERIC} text-data`} style={{ color }}>
        {rounded}
      </b>
      {showLabel && <span className="text-meta text-ink-low">{label}</span>}
    </span>
  );
}
