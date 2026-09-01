import { Eyebrow } from "../../../components/fc/primitives";
import type { Lead } from "../utils/pathRanking";

interface Props {
  leads: Lead[];
  onPick: (lead: Lead) => void;
}

const SEVERITY: Record<Lead["severity"], { label: string; cls: string }> = {
  high: { label: "Cao", cls: "text-risk-soft" },
  elevated: { label: "Nâng cao", cls: "text-warn-soft" },
  medium: { label: "Trung bình", cls: "text-ink-soft" },
};

/**
 * Gợi ý điều tra — bốn chỗ đáng nhìn trước.
 *
 * Bấm vào là focus thẳng vào node đó và bật đường tiền tương ứng nếu có, nên
 * analyst không phải tự đi tìm trong đám đỉnh.
 */
export function GraphInvestigationLeads({ leads, onPick }: Props) {
  if (!leads.length) return null;

  return (
    <div className="mt-4 animate-up">
      <Eyebrow className="mb-2">Gợi ý điều tra</Eyebrow>
      <ol className="flex flex-col gap-1.5">
        {leads.map((lead, i) => (
          <li key={lead.id}>
            <button
              type="button"
              onClick={() => onPick(lead)}
              className="flex w-full items-start gap-2.5 rounded-control border border-line bg-sunken px-2.5 py-2 text-left transition-colors hover:border-line-emphasis hover:bg-elev"
            >
              <span className="mt-[1px] flex h-4 w-4 flex-none items-center justify-center rounded-full bg-primary-soft font-mono text-3xs text-primary">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span className="min-w-0 flex-1 truncate text-xs font-medium text-ink-hi">{lead.title}</span>
                  <span className={`flex-none text-3xs ${SEVERITY[lead.severity].cls}`}>
                    {SEVERITY[lead.severity].label}
                  </span>
                </span>
                <span className="mt-0.5 block text-3xs leading-relaxed text-ink-low">{lead.reason}</span>
                {/* Tình trạng bằng chứng phải nằm ngay trên gợi ý: một đầu mối
                    chưa có liên kết quan sát được thì phải điều tra khác hẳn
                    một đầu mối đã có. */}
                <span
                  className={`mt-1 inline-block rounded px-1.5 py-px font-mono text-3xs ${
                    lead.evidence.startsWith("Thiếu")
                      ? "bg-warn/10 text-warn-soft"
                      : lead.evidence.startsWith("Suy luận")
                        ? "bg-agent/10 text-agent-soft"
                        : "bg-ok/10 text-ok-soft"
                  }`}
                >
                  {lead.evidence}
                </span>
              </span>
              <span className="mt-0.5 flex-none text-ink-dim">›</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
