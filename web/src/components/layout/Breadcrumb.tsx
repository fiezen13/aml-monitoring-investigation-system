import { Link } from "react-router-dom";

interface Crumb {
  label: string;
  to?: string;
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Đường dẫn điều hướng" className="mb-2 text-2xs text-ink-low">
      {items.map((item, i) => (
        <span key={`${item.label}-${i}`}>
          {i > 0 && <span className="mx-1.5">›</span>}
          {item.to ? (
            <Link to={item.to} className="transition-colors hover:text-ink-hi">
              {item.label}
            </Link>
          ) : (
            <span className="text-ink-mid">{item.label}</span>
          )}
        </span>
      ))}
    </nav>
  );
}
