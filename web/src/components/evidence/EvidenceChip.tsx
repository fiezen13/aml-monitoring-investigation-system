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

import { getEvidence } from "../../data/mockEvidence";
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
  const evidence = getEvidence(evidenceId);
  const label = evidence ? `${evidenceId} - ${evidence.title.split(" ").slice(0, 3).join(" ")}` : evidenceId;
  return (
    <button
      type="button"
      onClick={() => onOpen(evidenceId)}
      title={evidence ? `${evidence.title} · ${evidence.source}` : evidenceId}
      className="inline-flex items-center gap-1 rounded-control border border-primary/30 bg-primary-soft px-1.5 py-0.5 text-2xs font-medium text-primary transition-colors hover:border-primary/60"
    >
      {evidence ? KIND_ICON[evidence.kind] : <FileText size={11} aria-hidden />}
      {label}
    </button>
  );
}
