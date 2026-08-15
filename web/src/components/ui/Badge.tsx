import { AlertTriangle, CheckCircle2, CircleDot, Clock, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { TONE, type Tone } from "../../design/semantic";

/**
 * Nhãn trạng thái.
 *
 * Hợp nhất `common/Badges.StatusBadge` (nền tint + icon) và
 * `fc/primitives.Chip` (chỉ viền, không nền). Giữ cả hai dáng vì chúng phục vụ
 * hai chỗ khác nhau: `solid` cho bảng và danh sách — nơi nhãn phải bắt mắt qua
 * hàng chục dòng; `outline` cho inspector và HUD — nơi đã có nền riêng và một
 * khối tint nữa sẽ thành ba tầng màu chồng nhau.
 *
 * Trạng thái không bao giờ chỉ biểu diễn bằng màu: dáng `solid` luôn kèm icon,
 * và cả hai dáng luôn có nhãn chữ.
 */

const TONE_ICON: Record<Tone, ReactNode> = {
  neutral: <CircleDot size={11} aria-hidden />,
  primary: <ShieldCheck size={11} aria-hidden />,
  info: <CircleDot size={11} aria-hidden />,
  ok: <CheckCircle2 size={11} aria-hidden />,
  warn: <Clock size={11} aria-hidden />,
  risk: <AlertTriangle size={11} aria-hidden />,
  agent: <ShieldCheck size={11} aria-hidden />,
  token: <CircleDot size={11} aria-hidden />,
};

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  variant?: "solid" | "outline";
  /** Bỏ icon khi nhãn đã đủ rõ và chỗ hiển thị rất hẹp. */
  icon?: ReactNode | false;
  title?: string;
  className?: string;
}

export function Badge({
  tone = "neutral",
  children,
  variant = "solid",
  icon,
  title,
  className = "",
}: BadgeProps) {
  const spec = TONE[tone];
  const showIcon = variant === "solid" && icon !== false;
  const shape =
    variant === "solid"
      ? `border ${spec.surfaceClass}`
      : `rounded-chip border ${spec.borderClass} ${spec.textClass}`;

  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap px-1.5 py-0.5 text-meta font-medium ${
        variant === "solid" ? "rounded-control" : ""
      } ${shape} ${className}`}
    >
      {showIcon && (icon ?? TONE_ICON[tone])}
      {children}
    </span>
  );
}

/**
 * Chấm trạng thái có nhịp đập — chỉ báo "đang sống".
 *
 * Đây là lớp L0 của hệ chuyển động: gần như không thấy, nhưng nếu nó dừng thì
 * người trực ban biết luồng dữ liệu đã đứng.
 */
export function PulseDot({ tone = "ok", size = 7 }: { tone?: Tone; size?: number }) {
  const color = TONE[tone].base;
  return (
    <span
      className="inline-block flex-none animate-pulse rounded-full"
      style={{ width: size, height: size, background: color, boxShadow: `0 0 6px ${color}` }}
      aria-hidden
    />
  );
}

/** Thanh tiến độ mảnh — độ phủ bằng chứng, tỷ lệ hoàn thành, độ tin cậy. */
export function ProgressBar({
  value,
  tone = "info",
  className = "",
}: {
  value: number;
  tone?: Tone;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span className={`block h-1 overflow-hidden rounded-sm bg-line ${className}`}>
      <span
        className="block h-full rounded-sm transition-[width] duration-300"
        style={{ width: `${pct}%`, background: TONE[tone].base }}
      />
    </span>
  );
}
