import type { SarStatement as SarStatementType } from "../../types";
import { EvidenceChip } from "../evidence/EvidenceChip";

interface SARStatementProps {
  statement: SarStatementType;
  onOpenEvidence: (id: string) => void;
  /** Mã bằng chứng → nhãn nghiệp vụ, để chip không phải in mã thô. */
  evidenceLabels?: Record<string, string>;
}

/**
 * Một câu nhận định trong SAR — bắt buộc có evidence chip (NT1).
 * Câu không có bằng chứng sẽ bị bộ kiểm chứng chặn ở bước gửi phê duyệt.
 */
export function SARStatement({ statement, onOpenEvidence, evidenceLabels }: SARStatementProps) {
  return (
    <div className="rounded-control border border-line bg-elev p-3">
      <p className="text-body leading-relaxed text-ink-hi">{statement.text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {statement.evidenceIds.map((id) => (
          <EvidenceChip key={id} evidenceId={id} label={evidenceLabels?.[id]} onOpen={onOpenEvidence} />
        ))}
        {statement.highlight && (
          <span className="tabular rounded-control border border-info/30 bg-info/10 px-1.5 py-0.5 text-2xs text-info">
            {statement.highlight}
          </span>
        )}
      </div>
    </div>
  );
}
