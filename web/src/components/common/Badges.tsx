import { ShieldCheck, XCircle } from "lucide-react";
import type { ReactNode } from "react";

import type { Tone } from "../../design/semantic";
import { Badge } from "../ui/Badge";
import { RiskIndicator } from "../ui/RiskIndicator";

/**
 * Lớp tương thích — badge thật nằm ở `components/ui/Badge` và
 * `components/ui/RiskIndicator`.
 *
 * Điểm quan trọng nhất của việc chuyển tiếp này: `RiskBadge` cũ dùng ngưỡng
 * 75/50 riêng của nó, lệch với 80/60 mà phần còn lại của hệ thống dùng. Nay nó
 * chỉ còn là một lớp mỏng gọi `RiskIndicator`, nên không còn thang thứ hai nào
 * tồn tại trong repo.
 *
 * @deprecated Import từ `components/ui` cho code mới.
 */

type LegacyTone = "risk" | "warn" | "ok" | "info" | "muted" | "primary";

const TONE_MAP: Record<LegacyTone, Tone> = {
  risk: "risk",
  warn: "warn",
  ok: "ok",
  info: "info",
  muted: "neutral",
  primary: "primary",
};

export function StatusBadge({
  tone,
  label,
  title,
  icon,
}: {
  tone: LegacyTone;
  label: string;
  title?: string;
  icon?: ReactNode;
}) {
  return (
    <Badge tone={TONE_MAP[tone]} title={title} icon={icon}>
      {label}
    </Badge>
  );
}

export function RiskBadge({ score }: { score: number }) {
  return <RiskIndicator score={score} variant="badge" />;
}

export function RoleBadge({ label }: { label: string }) {
  return (
    <Badge tone="info" icon={<ShieldCheck size={11} aria-hidden />} className="uppercase tracking-wide">
      {label}
    </Badge>
  );
}

export function FailBadge({ label }: { label: string }) {
  return (
    <Badge tone="risk" icon={<XCircle size={11} aria-hidden />}>
      {label}
    </Badge>
  );
}
