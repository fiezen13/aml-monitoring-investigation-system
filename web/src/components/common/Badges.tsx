import {
  AlertTriangle,
  CheckCircle2,
  CircleDot,
  Clock,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import type { ReactNode } from "react";

type Tone = "risk" | "warn" | "ok" | "info" | "muted" | "primary";

const TONE_CLASS: Record<Tone, string> = {
  risk: "bg-risk/10 text-risk border-risk/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  ok: "bg-ok/10 text-ok border-ok/30",
  info: "bg-info/10 text-info border-info/30",
  muted: "bg-ink-low/10 text-ink-mid border-ink-low/30",
  primary: "bg-primary-soft text-primary border-primary/30",
};

const TONE_ICON: Record<Tone, ReactNode> = {
  risk: <AlertTriangle size={11} aria-hidden />,
  warn: <Clock size={11} aria-hidden />,
  ok: <CheckCircle2 size={11} aria-hidden />,
  info: <CircleDot size={11} aria-hidden />,
  muted: <CircleDot size={11} aria-hidden />,
  primary: <ShieldCheck size={11} aria-hidden />,
};

/**
 * Badge trạng thái — trạng thái không bao giờ chỉ biểu diễn bằng màu:
 * luôn có icon + nhãn chữ đi kèm.
 */
export function StatusBadge({
  tone,
  label,
  title,
  icon,
}: {
  tone: Tone;
  label: string;
  title?: string;
  icon?: ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-control border px-1.5 py-0.5 text-2xs font-medium ${TONE_CLASS[tone]}`}
    >
      {icon ?? TONE_ICON[tone]}
      {label}
    </span>
  );
}

/** Badge điểm rủi ro dạng ô số — màu theo ngưỡng, kèm tooltip giải thích. */
export function RiskBadge({ score }: { score: number }) {
  const tone =
    score >= 75
      ? "bg-risk/15 text-risk"
      : score >= 50
        ? "bg-warn/15 text-warn"
        : "bg-ok/15 text-ok";
  const label = score >= 75 ? "Rủi ro cao" : score >= 50 ? "Rủi ro trung bình" : "Rủi ro thấp";
  return (
    <span
      title={`${label} — điểm ${score}/100, luôn xem kèm yếu tố đóng góp (NT7)`}
      className={`tabular inline-flex min-w-[30px] items-center justify-center rounded-control px-1.5 py-0.5 text-2xs font-bold ${tone}`}
    >
      {score}
    </span>
  );
}

/** Độ tin cậy AI — phần trăm kèm thanh tiến độ nhỏ. */
export function ConfidenceBadge({ value }: { value: number }) {
  return (
    <div
      className="min-w-[54px]"
      title={`Độ tin cậy của mô hình: ${value}% — cần con người rà soát`}
    >
      <div className="tabular text-[12px] font-semibold text-ink-hi">
        {value}%
      </div>
      <div className="mt-0.5 h-[3px] w-full overflow-hidden rounded bg-line">
        <div
          className="h-full rounded bg-primary"
          style={{ width: `${value}%` }}
        />
      </div>
    </div>
  );
}

/** Badge vai trò người dùng. */
export function RoleBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-control border border-info/30 bg-info/10 px-1.5 py-0.5 text-2xs font-medium uppercase tracking-wide text-info">
      <ShieldCheck size={11} aria-hidden />
      {label}
    </span>
  );
}

export function FailBadge({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-control border border-risk/30 bg-risk/10 px-1.5 py-0.5 text-2xs font-medium text-risk">
      <XCircle size={11} aria-hidden />
      {label}
    </span>
  );
}
