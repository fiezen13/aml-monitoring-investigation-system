import { Loader2 } from "lucide-react";
import { motion, type HTMLMotionProps } from "motion/react";
import type { ReactNode } from "react";

import { transitions, useReduced } from "../../design/motion";

/**
 * Nút.
 *
 * Bốn cấp, và chỉ cấp `primary` được tô đặc — nếu mọi hành động đều teal thì
 * teal không còn nói được đâu là hành động chính của màn hình. Không có quầng
 * sáng ngoài: đây là phần mềm ngân hàng.
 *
 * Phản hồi khi bấm là lớp L1: 96% trong 80ms rồi trở lại. Đủ để ngón tay tin
 * rằng cú bấm đã tới, không đủ để thành hiệu ứng.
 */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANT: Record<Variant, string> = {
  primary: "bg-primary text-primary-on font-semibold hover:bg-primary-hover active:bg-primary-press",
  secondary: "border border-line-strong text-ink-soft hover:border-line-emphasis hover:bg-elev hover:text-ink-hi",
  ghost: "text-ink-soft hover:bg-elev hover:text-ink-hi",
  danger: "border border-risk/40 text-risk-soft hover:bg-risk/10 hover:border-risk/60",
};

const SIZE: Record<Size, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-meta",
  md: "h-8 gap-2 px-3 text-data",
};

// Kế thừa props của `motion.button` chứ không của `<button>` thuần: hai bên
// định nghĩa `onDrag` khác nhau (kéo-thả HTML5 với cử chỉ kéo của Motion), và
// trải props DOM vào motion component sẽ đỏ ở đúng chỗ đó.
interface Props extends Omit<HTMLMotionProps<"button">, "children"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  children?: ReactNode;
}

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  children,
  className = "",
  disabled,
  ...rest
}: Props) {
  const reduced = useReduced();
  const isDisabled = disabled || loading;

  return (
    <motion.button
      whileTap={reduced || isDisabled ? undefined : { scale: 0.96 }}
      transition={transitions.feedback}
      disabled={isDisabled}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-control transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${VARIANT[variant]} ${SIZE[size]} ${className}`}
      {...rest}
    >
      {loading ? <Loader2 size={13} className="animate-spin" aria-hidden /> : icon}
      {children}
    </motion.button>
  );
}

interface IconButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  /** Bắt buộc: nút chỉ có icon không có tên nào khác cho trình đọc màn hình. */
  label: string;
  icon: ReactNode;
  variant?: Variant;
  size?: Size;
  active?: boolean;
}

export function IconButton({
  label,
  icon,
  variant = "ghost",
  size = "md",
  active = false,
  className = "",
  ...rest
}: IconButtonProps) {
  const reduced = useReduced();
  const box = size === "sm" ? "h-7 w-7" : "h-8 w-8";

  return (
    <motion.button
      whileTap={reduced ? undefined : { scale: 0.94 }}
      transition={transitions.feedback}
      aria-label={label}
      title={label}
      aria-pressed={active || undefined}
      className={`grid flex-none place-items-center rounded-control transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
        active ? "border border-primary/40 bg-primary-soft text-primary" : VARIANT[variant]
      } ${box} ${className}`}
      {...rest}
    >
      {icon}
    </motion.button>
  );
}
