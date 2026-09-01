import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { TEXT } from "../../design/typography";
import { inspectorVariants, popVariants, safeVariants, transitions, useReduced } from "../../design/motion";
import { IconButton } from "./Button";

/**
 * Các lớp phủ: popover, tooltip, drawer, modal, inspector.
 *
 * Tất cả dùng chung nền `raised`, viền `line-strong` và shadow `popover` — đây
 * là những phần tử duy nhất trong console được đổ bóng, vì chúng thực sự nổi
 * trên mặt phẳng nội dung. Panel và thẻ lấy chiều sâu từ tầng nền.
 */

/** Đóng khi bấm ra ngoài hoặc nhấn Escape — dùng chung cho popover và dropdown. */
export function useDismiss(open: boolean, onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const onPointer = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    // `pointerdown` chứ không `click`: bấm rồi kéo ra ngoài vẫn phải đóng, và
    // `click` bắn sau khi nội dung bên dưới đã kịp phản ứng.
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open, onClose]);

  return ref;
}

interface PopoverProps {
  open: boolean;
  onClose: () => void;
  /** Nút mở popover; nhận sẵn `aria-expanded`. */
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
  width?: number;
  className?: string;
}

export function Popover({ open, onClose, trigger, children, align = "right", width = 280, className = "" }: PopoverProps) {
  const reduced = useReduced();
  const ref = useDismiss(open, onClose);

  return (
    <div ref={ref} className={`relative ${className}`}>
      {trigger}
      <AnimatePresence>
        {open && (
          <motion.div
            variants={safeVariants(popVariants, reduced)}
            initial="initial"
            animate="animate"
            exit="exit"
            style={{ width, transformOrigin: align === "right" ? "top right" : "top left" }}
            className={`fc-raised absolute top-full z-dropdown mt-1.5 p-3 ${
              align === "right" ? "right-0" : "left-0"
            }`}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Tooltip nhẹ, hiện sau 300ms.
 *
 * Không thay thế `title` cho nội dung dài — nó chỉ dành cho nhãn ngắn của nút
 * chỉ có icon và của các ô bị cắt bớt.
 */
export function Tooltip({
  label,
  children,
  side = "right",
  className = "",
}: {
  label: string;
  children: ReactNode;
  side?: "right" | "top" | "bottom";
  className?: string;
}) {
  const reduced = useReduced();
  const [open, setOpen] = useState(false);
  const timer = useRef<number | null>(null);

  const show = () => {
    timer.current = window.setTimeout(() => setOpen(true), 300);
  };
  const hide = () => {
    if (timer.current) window.clearTimeout(timer.current);
    setOpen(false);
  };

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const position =
    side === "right"
      ? "left-full top-1/2 ml-2 -translate-y-1/2"
      : side === "top"
        ? "bottom-full left-1/2 mb-1.5 -translate-x-1/2"
        : "top-full left-1/2 mt-1.5 -translate-x-1/2";

  return (
    <span
      className={`relative inline-flex ${className}`}
      onPointerEnter={show}
      onPointerLeave={hide}
      onFocus={show}
      onBlur={hide}
    >
      {children}
      <AnimatePresence>
        {open && (
          <motion.span
            role="tooltip"
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={reduced ? { duration: 0.01 } : transitions.feedback}
            className={`fc-raised pointer-events-none absolute z-dropdown whitespace-nowrap px-2 py-1 text-meta text-ink-hi ${position}`}
          >
            {label}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  );
}

interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  width?: number;
}

/** Ngăn kéo trượt từ mép phải — dùng cho bằng chứng và chi tiết phụ. */
export function Drawer({ open, onClose, title, children, width = 420 }: DrawerProps) {
  const reduced = useReduced();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={reduced ? { duration: 0.01 } : transitions.state}
            onClick={onClose}
            className="fixed inset-0 z-drawer bg-scrim"
            aria-hidden
          />
          <motion.aside
            role="dialog"
            aria-label={typeof title === "string" ? title : undefined}
            initial={reduced ? { opacity: 0 } : { x: width }}
            animate={reduced ? { opacity: 1 } : { x: 0 }}
            exit={reduced ? { opacity: 0 } : { x: width }}
            transition={reduced ? { duration: 0.01 } : transitions.layout}
            style={{ width }}
            className="fixed inset-y-0 right-0 z-drawer flex max-w-[92vw] flex-col border-l border-line-strong bg-side shadow-modal"
          >
            <header className="flex flex-none items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className={TEXT.h3}>{title}</div>
              <IconButton label="Đóng" icon={<X size={15} />} onClick={onClose} size="sm" />
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Modal({ open, onClose, title, children, footer, width = 520 }: ModalProps) {
  const reduced = useReduced();

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={reduced ? { duration: 0.01 } : transitions.state}
          className="fixed inset-0 z-modal grid place-items-center bg-scrim p-4"
          onClick={onClose}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={typeof title === "string" ? title : undefined}
            initial={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.97, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, scale: 0.98 }}
            transition={reduced ? { duration: 0.01 } : transitions.state}
            onClick={(event) => event.stopPropagation()}
            style={{ width }}
            className="flex max-h-[86vh] w-full max-w-[92vw] flex-col rounded-panel border border-line-strong bg-raised shadow-modal"
          >
            <header className="flex flex-none items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className={TEXT.h3}>{title}</div>
              <IconButton label="Đóng" icon={<X size={15} />} onClick={onClose} size="sm" />
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
            {footer && (
              <footer className="flex flex-none items-center justify-end gap-2 border-t border-line px-4 py-3">
                {footer}
              </footer>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/**
 * Cột chi tiết cố định bên phải không gian làm việc.
 *
 * Khác `Drawer` ở chỗ nó nằm trong dòng chảy bố cục chứ không phủ lên trên:
 * trong màn điều tra, analyst cần nhìn đồ thị và bảng chi tiết cùng lúc.
 */
export function Inspector({
  children,
  className = "",
  animateKey,
}: {
  children: ReactNode;
  className?: string;
  /** Đổi khoá khi đối tượng đang xem đổi — nội dung sẽ trượt vào lại. */
  animateKey?: string | null;
}) {
  const reduced = useReduced();
  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={animateKey ?? "empty"}
        variants={safeVariants(inspectorVariants, reduced)}
        initial="initial"
        animate="animate"
        exit="exit"
        className={className}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
}
