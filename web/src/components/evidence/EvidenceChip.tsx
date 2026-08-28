import {
  Calculator,
  FileText,
  Globe,
  IdCard,
  Link2,
  MapPin,
  Network,
  ScanSearch,
  Share2,
} from "lucide-react";
import type { ReactNode } from "react";

import type { EvidenceKind } from "../../types";

const KIND_ICON: Record<EvidenceKind, ReactNode> = {
  statement: <FileText size={11} aria-hidden />,
  ownership: <Link2 size={11} aria-hidden />,
  geo: <MapPin size={11} aria-hidden />,
  opensource: <Globe size={11} aria-hidden />,
  id_document: <IdCard size={11} aria-hidden />,
  calculation: <Calculator size={11} aria-hidden />,
  screening: <ScanSearch size={11} aria-hidden />,
  graph: <Share2 size={11} aria-hidden />,
  network_log: <Network size={11} aria-hidden />,
};

interface EvidenceChipProps {
  evidenceId: string;
  /** Nhãn nghiệp vụ. Không truyền thì chip ghi "Bằng chứng" chứ KHÔNG in mã thô. */
  label?: string;
  onOpen: (evidenceId: string) => void;
}

/**
 * Chip bằng chứng — mọi nhận định AI phải trỏ được về một chip (NT1).
 * Click mở Evidence Drawer.
 */
export function EvidenceChip({ evidenceId, label, onOpen }: EvidenceChipProps) {
  // Mã bằng chứng (EV-1f321dc25a63…) là định danh nội bộ, không nói gì với
  // chuyên viên. Nó vẫn cần cho việc truy vết, nên chuyển vào tooltip — cùng
  // quy ước đã dùng ở trang Chi tiết cảnh báo cho mã yếu tố đóng góp.
  const text = label ?? "Bằng chứng";
  return (
    <button
      type="button"
      onClick={() => onOpen(evidenceId)}
      title={`Mở bằng chứng ${evidenceId}`}
      className="inline-flex items-center gap-1 rounded-control border border-info/30 bg-info/[0.08] px-1.5 py-0.5 text-2xs font-medium text-info-soft transition-colors hover:border-info/60"
    >
      {KIND_ICON.statement}
      {text}
    </button>
  );
}
