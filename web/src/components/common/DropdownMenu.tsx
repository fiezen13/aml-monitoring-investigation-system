import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";

interface DropdownMenuProps {
  label: ReactNode;
  items: { id: string; label: string; onSelect?: () => void; disabled?: boolean }[];
  align?: "left" | "right";
  buttonClassName?: string;
}

export function DropdownMenu({
  label,
  items,
  align = "left",
  buttonClassName = "",
}: DropdownMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className={
          buttonClassName ||
          "inline-flex items-center gap-1.5 rounded-control border border-line bg-elev px-2.5 py-1.5 text-body font-medium text-ink-hi hover:border-line-emphasis"
        }
      >
        {label}
        <ChevronDown size={13} aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className={`absolute top-full z-40 mt-1 min-w-[180px] rounded-panel border border-line bg-elev py-1 shadow-xl ${
            align === "right" ? "right-0" : "left-0"
          }`}
        >
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitem"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect?.();
              }}
              className="block w-full px-3 py-1.5 text-left text-body text-ink-mid hover:bg-panel hover:text-ink-hi disabled:cursor-not-allowed disabled:opacity-40"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
