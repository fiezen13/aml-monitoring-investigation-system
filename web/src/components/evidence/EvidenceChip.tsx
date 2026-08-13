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
  onOpen: (evidenceId: string) => void;
}

/**
 * Chip bằng chứng — mọi nhận định AI phải trỏ được về một chip (NT1).
 * Click mở Evidence Drawer.
 */
export function EvidenceChip({ evidenceId, onOpen }: EvidenceChipProps) {
  const label = evidenceId;
  return (
    <button
      type="button"
      onClick={() => onOpen(evidenceId)}
      title={`Mở bằng chứng ${evidenceId} từ API`}
      className="inline-flex items-center gap-1 rounded-control border border-info/30 bg-info/[0.08] px-1.5 py-0.5 text-2xs font-medium text-info-soft transition-colors hover:border-info/60"
    >
      {KIND_ICON.statement}
      {label}
    </button>
  );
}
