import { motion } from "motion/react";
import { useId } from "react";
import type { ReactNode } from "react";

import { transitions, useReduced } from "../../design/motion";

/**
 * Tab và bộ chọn phân đoạn.
 *
 * Cả hai dùng chung một kỹ thuật: chỉ báo "đang chọn" là MỘT phần tử duy nhất
 * trượt giữa các mục (`layoutId` của Motion), không phải mỗi mục tự bật/tắt nền
 * của mình. Khác biệt không nằm ở thẩm mỹ — chỉ báo trượt giữ được liên tục
 * không gian, mắt bám theo được nó và biết mình vừa đi từ đâu sang đâu.
 */

interface TabItem {
  id: string;
  label: ReactNode;
  /** Số việc tồn đọng hiện cạnh nhãn. */
  count?: number;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
}

export function Tabs({ tabs, active, onChange, className = "" }: TabsProps) {
  const reduced = useReduced();
  const groupId = useId();

  return (
    <div role="tablist" className={`flex gap-1 border-b border-line ${className}`}>
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(tab.id)}
            className={`relative -mb-px px-3 py-2 text-body font-medium transition-colors ${
              isActive ? "text-ink-hi" : "text-ink-soft hover:text-ink-mid"
            }`}
          >
            <span className="inline-flex items-center gap-1.5">
              {tab.label}
              {tab.count != null && (
                <span className="tabular rounded-chip bg-elev px-1.5 font-mono text-micro leading-[16px] text-ink-low">
                  {tab.count}
                </span>
              )}
            </span>
            {isActive && (
              <motion.span
                layoutId={`${groupId}-tab-underline`}
                transition={reduced ? { duration: 0.01 } : transitions.state}
                className="absolute inset-x-0 -bottom-px h-0.5 rounded-sm bg-primary"
                aria-hidden
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

interface SegmentedProps<T extends string> {
  options: { value: T; label: ReactNode; icon?: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  /** Tên cho trình đọc màn hình — bộ chọn này thay cho một nhóm radio. */
  label: string;
  size?: "sm" | "md";
  className?: string;
}

/**
 * Bộ chọn phân đoạn — dùng cho các lựa chọn loại trừ nhau và luôn hiện hết:
 * 2D/3D, mức độ, khoảng thời gian.
 */
export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "md",
  className = "",
}: SegmentedProps<T>) {
  const reduced = useReduced();
  const groupId = useId();
  const pad = size === "sm" ? "px-2 py-1 text-meta" : "px-2.5 py-1.5 text-data";

  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`inline-flex flex-none gap-0.5 rounded-control border border-line-strong bg-sunken p-0.5 ${className}`}
    >
      {options.map((option) => {
        const isActive = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={isActive}
            onClick={() => onChange(option.value)}
            className={`relative inline-flex items-center gap-1.5 rounded-sm font-medium transition-colors ${pad} ${
              isActive ? "text-primary" : "text-ink-soft hover:text-ink-hi"
            }`}
          >
            {isActive && (
              <motion.span
                layoutId={`${groupId}-segment`}
                transition={reduced ? { duration: 0.01 } : transitions.state}
                className="absolute inset-0 rounded-sm border border-primary/30 bg-primary-soft"
                aria-hidden
              />
            )}
            <span className="relative z-hud inline-flex items-center gap-1.5">
              {option.icon}
              {option.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
