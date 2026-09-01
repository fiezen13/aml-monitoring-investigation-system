import { Check, Search } from "lucide-react";
import { motion } from "motion/react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useId } from "react";

import { transitions, useReduced } from "../../design/motion";

/**
 * Ô nhập liệu và các control biểu mẫu.
 *
 * Mọi control dùng chung một dáng: nền lõm, viền `line-strong`, bo 7px, cao
 * 28/32px. Trước đây mỗi trang tự viết — có chỗ `bg-elev`, có chỗ `bg-sunken`,
 * có chỗ `border-line`, có chỗ không viền — nên hai ô cạnh nhau trong cùng một
 * thanh lọc trông như thuộc hai hệ thống.
 */

const CONTROL =
  "w-full rounded-control border border-line-strong bg-sunken px-2.5 text-data text-ink-hi outline-none transition-colors placeholder:text-ink-dim hover:border-line-emphasis focus:border-primary/60 focus:shadow-focus disabled:opacity-45";

export function Label({ htmlFor, children }: { htmlFor?: string; children: ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-meta font-medium text-ink-low">
      {children}
    </label>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: ReactNode;
}

export function Input({ label, hint, className = "", id, ...rest }: InputProps) {
  const autoId = useId();
  const inputId = id ?? autoId;
  return (
    <div className="min-w-0">
      {label && <Label htmlFor={inputId}>{label}</Label>}
      <input id={inputId} className={`h-8 ${CONTROL} ${className}`} {...rest} />
      {hint && <div className="mt-1 text-micro text-ink-dim">{hint}</div>}
    </div>
  );
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  children: ReactNode;
}

export function Select({ label, children, className = "", id, ...rest }: SelectProps) {
  const autoId = useId();
  const selectId = id ?? autoId;
  return (
    <div className="min-w-0">
      {label && <Label htmlFor={selectId}>{label}</Label>}
      <select id={selectId} className={`h-8 pr-6 ${CONTROL} ${className}`} {...rest}>
        {children}
      </select>
    </div>
  );
}

interface SearchProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  shortcutHint?: string;
  className?: string;
  "aria-label"?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Tìm kiếm…",
  shortcutHint,
  className = "",
  "aria-label": ariaLabel,
}: SearchProps) {
  return (
    <div className={`relative min-w-0 ${className}`}>
      <Search
        size={13}
        aria-hidden
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-dim"
      />
      <input
        type="search"
        value={value}
        aria-label={ariaLabel ?? placeholder}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className={`h-8 pl-7 ${shortcutHint ? "pr-9" : ""} ${CONTROL}`}
      />
      {shortcutHint && (
        <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded-sm border border-line-strong px-1 font-mono text-micro text-ink-dim">
          {shortcutHint}
        </kbd>
      )}
    </div>
  );
}

interface CheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}

export function Checkbox({ checked, onChange, label, disabled }: CheckboxProps) {
  return (
    <label className={`inline-flex items-center gap-2 text-data ${disabled ? "opacity-45" : "cursor-pointer"}`}>
      <span className="relative grid h-4 w-4 flex-none place-items-center">
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange(event.target.checked)}
          className="peer absolute inset-0 cursor-pointer opacity-0"
        />
        <span
          aria-hidden
          className={`grid h-4 w-4 place-items-center rounded-sm border transition-colors ${
            checked ? "border-primary bg-primary text-primary-on" : "border-line-strong bg-sunken text-transparent"
          } peer-focus-visible:shadow-focus`}
        >
          <Check size={11} strokeWidth={3} />
        </span>
      </span>
      <span className="text-ink-mid">{label}</span>
    </label>
  );
}

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  /**
   * Màu của núm khi bật. Mặc định là accent, nhưng bảng lọc lớp dòng tiền cố ý
   * truyền màu của chính lớp đó: sáu công tắc cùng một sắc teal chỉ nói được
   * "đang bật", còn mang màu lớp thì chúng nói luôn "đang bật cái gì".
   */
  color?: string;
  size?: "sm" | "md";
}

export function Switch({ checked, onChange, label, color, size = "md" }: SwitchProps) {
  const reduced = useReduced();
  const track = size === "sm" ? "h-3.5 w-[30px]" : "h-4 w-[34px]";
  const knob = size === "sm" ? 9 : 11;
  const travel = size === "sm" ? 18 : 20;
  const on = color ?? "var(--accent)";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative flex-none rounded-full border border-line-strong transition-colors ${track}`}
      style={{ background: checked ? `${color ?? "rgba(32,199,167,1)"}2E` : "transparent" }}
    >
      <motion.span
        aria-hidden
        className="absolute top-1/2 rounded-full"
        style={{ width: knob, height: knob, background: checked ? on : "var(--ink-dim)" }}
        animate={{ x: checked ? travel : 2, y: "-50%" }}
        transition={reduced ? { duration: 0.01 } : transitions.feedback}
      />
    </button>
  );
}
