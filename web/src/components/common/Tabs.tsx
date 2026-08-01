interface TabsProps {
  tabs: { id: string; label: string }[];
  active: string;
  onChange: (id: string) => void;
  variant?: "underline" | "pill";
}

export function Tabs({ tabs, active, onChange, variant = "underline" }: TabsProps) {
  if (variant === "pill") {
    return (
      <div className="inline-flex gap-1 rounded-control border border-line bg-elev p-0.5">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            className={`rounded px-2.5 py-1 text-2xs font-semibold uppercase tracking-wide transition-colors ${
              active === tab.id
                ? "bg-primary text-app"
                : "text-ink-mid hover:text-ink-hi"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
    );
  }
  return (
    <div className="flex gap-1 border-b border-line" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={active === tab.id}
          onClick={() => onChange(tab.id)}
          className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
            active === tab.id
              ? "border-primary text-ink-hi"
              : "border-transparent text-ink-mid hover:text-ink-hi"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
