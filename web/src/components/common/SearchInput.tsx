import { Search } from "lucide-react";

interface SearchInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  shortcutHint?: string;
}

export function SearchInput({
  value,
  onChange,
  placeholder = "Tìm kiếm...",
  className = "",
  shortcutHint,
}: SearchInputProps) {
  return (
    <div className={`relative ${className}`}>
      <Search
        size={14}
        aria-hidden
        className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-low"
      />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-control border border-line bg-elev py-1.5 pl-8 pr-8 text-[13px] text-ink-hi placeholder:text-ink-low focus:border-primary/50 focus:outline-none"
      />
      {shortcutHint && (
        <kbd className="absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line px-1 text-2xs text-ink-low">
          {shortcutHint}
        </kbd>
      )}
    </div>
  );
}
