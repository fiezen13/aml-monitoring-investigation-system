import type { ReactNode } from "react";

import { getRiskTone } from "../../design/risk";
import type { Tone } from "../../design/semantic";
import { C } from "../../design/palette";
import { Badge, ProgressBar as UiProgressBar, PulseDot as UiPulseDot } from "../ui/Badge";
import { MetricCard, StatTile as UiStatTile } from "../ui/MetricCard";
import { Panel as UiPanel, Eyebrow as UiEyebrow } from "../ui/Panel";
import { RiskIndicator } from "../ui/RiskIndicator";
import { EmptyState, TableSkeleton } from "../ui/States";
import { TEXT } from "../../design/typography";

/**
 * Lớp tương thích cho bộ primitive cũ của nhóm trang `fc`.
 *
 * Mọi thứ ở đây đã là lớp mỏng bọc `components/ui`. Giữ lại vì chín trang vẫn
 * import chúng và vì vài chỗ truyền màu thô (`valueColor={C.warn}`) — thứ mà bộ
 * mới cố ý không nhận nữa: màu phải đến từ `tone`, không phải từ chỗ gọi.
 *
 * @deprecated Import từ `components/ui` cho code mới.
 */

/** Suy ngược từ mã màu thô về tone ngữ nghĩa, để bản cũ vẫn ra đúng màu. */
function toneOfColor(color?: string): Tone {
  switch (color) {
    case C.risk:
    case C.riskSoft:
      return "risk";
    case C.warn:
    case C.warnSoft:
      return "warn";
    case C.ok:
    case C.okSoft:
      return "ok";
    case C.info:
    case C.infoSoft:
      return "info";
    case C.agent:
    case C.agentSoft:
      return "agent";
    case C.token:
      return "token";
    case C.primary:
    case C.primaryHi:
      return "primary";
    default:
      return "neutral";
  }
}

export function Eyebrow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <UiEyebrow className={className}>{children}</UiEyebrow>;
}

export function ScreenTitle({ title, meta }: { title: string; meta?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2.5">
      <h1 className={`m-0 ${TEXT.h1}`}>{title}</h1>
      {meta && <span className="text-meta text-ink-low">{meta}</span>}
    </div>
  );
}

export function KpiCard({
  label,
  value,
  delta,
  valueColor,
  onClick,
}: {
  label: string;
  value: ReactNode;
  delta?: ReactNode;
  valueColor?: string;
  deltaColor?: string;
  onClick?: () => void;
}) {
  return (
    <MetricCard
      label={label}
      // Truyền thẳng, KHÔNG String(): `value` khai là ReactNode nên nơi gọi
      // truyền cả JSX vào, và String() biến JSX thành "[object Object]" — đúng
      // thứ đang hiện ở ô "Phiên bản mô hình" trên trang Đánh giá chuẩn.
      value={value ?? "—"}
      tone={toneOfColor(valueColor)}
      note={delta}
      onClick={onClick}
    />
  );
}

export function StatTile({
  label,
  value,
  sub,
  valueColor,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  valueColor?: string;
  subColor?: string;
}) {
  return <UiStatTile label={label} value={value} sub={sub} tone={toneOfColor(valueColor)} />;
}

export function Chip({
  children,
  color,
  className = "",
  title,
}: {
  children: ReactNode;
  color?: string;
  className?: string;
  title?: string;
}) {
  return (
    <Badge tone={toneOfColor(color)} variant="outline" title={title} className={className}>
      {children}
    </Badge>
  );
}

export function RiskScore({ score, width = 44 }: { score: number; width?: number }) {
  return <RiskIndicator score={score} width={width} />;
}

export function ProgressBar({ value, color }: { value: number; color?: string }) {
  const tone = toneOfColor(color);
  return <UiProgressBar value={value} tone={tone === "neutral" ? "info" : tone} />;
}

export function PulseDot({ color, size = 7 }: { color?: string; size?: number }) {
  const tone = toneOfColor(color);
  return <UiPulseDot tone={tone === "neutral" ? "ok" : tone} size={size} />;
}

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
    <UiPanel
      title={title}
      subtitle={subtitle}
      actions={actions}
      className={className}
      bodyClassName={bodyClassName}
    >
      {children}
    </UiPanel>
  );
}

export function Empty({ text, hint }: { text: string; hint?: string }) {
  return <EmptyState title={text} detail={hint ?? ""} />;
}

export function Skeleton({ rows = 6 }: { rows?: number }) {
  return <TableSkeleton rows={rows} />;
}

/** Nhóm rủi ro của một điểm số — vài chỗ cũ cần tone để tô nền hàng. */
export { getRiskTone };
