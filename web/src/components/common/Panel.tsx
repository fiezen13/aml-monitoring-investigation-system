import type { ReactNode } from "react";

interface PanelProps {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
  elevated?: boolean;
}

export function Panel({
  title,
  action,
  children,
  className = "",
  padded = true,
  elevated = false,
}: PanelProps) {
  return (
    <section
      className={`rounded-panel border border-line ${elevated ? "bg-elev" : "bg-panel"} ${className}`}
    >
      {(title || action) && (
        <header className="flex items-center justify-between border-b border-line px-4 py-3">
          <div className="text-[13px] font-semibold text-ink-hi">{title}</div>
          {action}
        </header>
      )}
      <div className={padded ? "p-4" : ""}>{children}</div>
    </section>
  );
}
