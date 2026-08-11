import { ScanSearch } from "lucide-react";

import type { ScreeningResult } from "../../types";
import { StatusBadge } from "./Badges";

const MATCH_LABEL: Record<ScreeningResult["matchType"], { label: string; tone: "risk" | "warn" | "ok" | "info" }> = {
  exact: { label: "Trùng khớp chính xác", tone: "risk" },
  strong: { label: "Trùng khớp mạnh", tone: "risk" },
  near_miss: { label: "Gần giống (near miss)", tone: "warn" },
  none: { label: "Không trùng khớp", tone: "ok" },
};

/** Kết quả đối chiếu PEP / trừng phạt — luôn hiện nguồn Screening Service. */
export function ScreeningResultCard({ result }: { result: ScreeningResult }) {
  const match = MATCH_LABEL[result.matchType];
  return (
    <div className="rounded-panel border border-line bg-elev p-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ScanSearch size={14} className="text-info" aria-hidden />
          <span className="text-[13px] font-semibold text-ink-hi">{result.listName}</span>
          <span className="tabular text-2xs text-ink-low">{result.listVersion}</span>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge tone={match.tone} label={match.label} />
          <span className="tabular text-[13px] font-bold text-ink-hi">
            {result.score.toLocaleString("vi-VN", { minimumFractionDigits: 2 })}
          </span>
        </div>
      </div>
      <div className="mt-2.5 grid grid-cols-2 gap-2 text-2xs">
        <div>
          <div className="mb-1 uppercase tracking-wide text-ink-low">Trường trùng khớp</div>
          {result.matchedFields.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {result.matchedFields.map((f) => (
                <span key={f} className="rounded bg-ok/10 px-1.5 py-0.5 text-ok">
                  {f}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-ink-low">—</span>
          )}
        </div>
        <div>
          <div className="mb-1 uppercase tracking-wide text-ink-low">Trường lệch</div>
          {result.mismatchedFields.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {result.mismatchedFields.map((f) => (
                <span key={f} className="rounded bg-risk/10 px-1.5 py-0.5 text-risk">
                  {f}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-ink-low">—</span>
          )}
        </div>
      </div>
      {result.alias && (
        <div className="mt-2 text-2xs text-ink-mid">
          Bí danh: <span className="text-ink-hi">{result.alias}</span>
        </div>
      )}
      <p className="mt-2 text-2xs leading-relaxed text-ink-mid">{result.explanation}</p>
      <p className="mt-1.5 text-2xs text-ink-low">Nguồn: {result.source}</p>
    </div>
  );
}
