import type { ReactNode } from "react";

import { C, riskColor } from "../../design/palette";

/**
 * Các khối nhỏ lặp lại ở hầu hết màn hình. Gom vào một file để một thay đổi
 * thị giác (ví dụ bo góc thẻ KPI) chỉ phải sửa một chỗ.
 */

/** Nhãn nhóm viết hoa, đứng đầu mỗi cụm nội dung. */
export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`fc-eyebrow ${className}`}>{children}</div>;
}

/** Tiêu đề màn hình kèm dòng ngữ cảnh bên cạnh. */
export function ScreenTitle({ title, meta }: { title: string; meta?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2.5">
      <h1 className="m-0 text-3xl font-semibold tracking-[-0.01em] text-ink-hi">{title}</h1>
      {meta && <span className="text-sm text-ink-low">{meta}</span>}
    </div>
  );
}

/**
 * Thẻ chỉ số. `delta` là dòng biến động bên dưới; màu do chỗ gọi quyết định vì
 * "tăng" có thể là tốt (case đã đóng) hoặc xấu (alert tồn đọng).
 */
export function KpiCard({
  label,
  value,
  delta,
  valueColor = C.inkHi,
  deltaColor = C.inkLow,
  onClick,
}: {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  valueColor?: string;
  deltaColor?: string;
  onClick?: () => void;
}) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      className={`fc-quiet px-3.5 py-3 text-left transition-colors ${
        onClick ? "cursor-pointer hover:bg-elev" : ""
      }`}
    >
      <div className="fc-eyebrow truncate-1">{label}</div>
      <div className="tabular mt-1.5 font-mono text-4xl font-semibold leading-none" style={{ color: valueColor }}>
        {value}
      </div>
      {delta != null && (
        <div className="mt-1.5 text-2xs" style={{ color: deltaColor }}>
          {delta}
        </div>
      )}
    </Tag>
  );
}

/** Ô số liệu nhỏ dùng trong sidebar và inspector. */
export function StatTile({
  label,
  value,
  sub,
  valueColor = C.inkHi,
  subColor = C.inkLow,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueColor?: string;
  subColor?: string;
}) {
  return (
    <div className="fc-quiet min-w-0 px-2.5 py-2">
      <div className="truncate-1 text-2xs text-ink-low">{label}</div>
      <div className="tabular truncate-1 mt-0.5 font-mono text-2xl font-semibold" style={{ color: valueColor }}>
        {value}
      </div>
      {sub != null && (
        <div className="text-3xs" style={{ color: subColor }}>
          {sub}
        </div>
      )}
    </div>
  );
}

/** Viên thuốc trạng thái — viền và chữ cùng màu, nền trong suốt. */
export function Chip({
  children,
  color = C.inkSoft,
  className = "",
  title,
}: {
  children: ReactNode;
  color?: string;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`fc-chip whitespace-nowrap ${className}`}
      style={{ color, borderColor: `${color}55` }}
    >
      {children}
    </span>
  );
}

/**
 * Điểm rủi ro kèm thanh mức độ. Thanh dài theo điểm và đổi màu theo ngưỡng —
 * đọc được cả khi liếc nhanh qua một bảng dài.
 */
export function RiskScore({ score, width = 44 }: { score: number; width?: number }) {
  const color = riskColor(score);
  const pct = `${Math.max(0, Math.min(100, score))}%`;
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="h-1 flex-1 rounded-sm"
        style={{
          maxWidth: width,
          background: `linear-gradient(90deg, ${color} ${pct}, #1D2A35 ${pct})`,
        }}
      />
      <b className="tabular font-mono text-xs" style={{ color }}>
        {score}
      </b>
    </span>
  );
}

/** Thanh tiến độ mảnh, dùng cho độ phủ evidence và tỷ lệ hoàn thành. */
export function ProgressBar({ value, color = C.info }: { value: number; color?: string }) {
  const pct = `${Math.max(0, Math.min(100, value))}%`;
  return (
    <span
      className="block h-1 rounded-sm"
      style={{ background: `linear-gradient(90deg, ${color} ${pct}, #1D2A35 ${pct})` }}
    />
  );
}

/** Chấm tròn có quầng sáng — chỉ báo trạng thái đang chạy. */
export function PulseDot({ color = C.ok, size = 7 }: { color?: string; size?: number }) {
  return (
    <span
      className="inline-block flex-none animate-pulse rounded-full"
      style={{ width: size, height: size, background: color, boxShadow: `0 0 6px ${color}` }}
    />
  );
}

/** Khối nội dung có tiêu đề — bản rút gọn của ChartCard cho nội dung không phải biểu đồ. */
export function Panel({
  title,
  subtitle,
  actions,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`overflow-hidden rounded-panel border border-line bg-panel ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-start gap-2 px-3.5 pb-2 pt-3">
          <div className="min-w-0 flex-1">
            {title && <div className="text-xl font-semibold leading-tight text-ink-hi">{title}</div>}
            {subtitle && <div className="mt-px text-2xs text-ink-low">{subtitle}</div>}
          </div>
          {actions && <div className="flex flex-none gap-1.5">{actions}</div>}
        </header>
      )}
      <div className={`px-3.5 pb-3 ${title ? "" : "pt-3"} ${bodyClassName}`}>{children}</div>
    </section>
  );
}

/** Trạng thái rỗng thống nhất cho bảng và danh sách. */
export function Empty({ text, hint }: { text: string; hint?: string }) {
  return (
    <div className="grid place-items-center px-4 py-10 text-center text-sm leading-relaxed text-ink-low">
      <div>
        <div className="mb-1 text-lg text-ink-dim">◌</div>
        {text}
        {hint && (
          <>
            <br />
            <span className="text-2xs text-ink-dim">{hint}</span>
          </>
        )}
      </div>
    </div>
  );
}

/** Khung tải cho bảng — giữ đúng chiều cao để bố cục không nhảy khi có dữ liệu. */
export function Skeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-1.5 p-3" aria-hidden>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-6 animate-pulse rounded-control bg-elev/60" />
      ))}
    </div>
  );
}
