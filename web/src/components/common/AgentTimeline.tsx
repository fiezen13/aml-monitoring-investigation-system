import { Check, CircleDashed, Loader2 } from "lucide-react";

import type { CaseTimelineStep } from "../../types";

/** Luồng xử lý hồ sơ của tác tử — 9 bước điều tra rút gọn theo Hình 4. */
export function AgentTimeline({ steps }: { steps: CaseTimelineStep[] }) {
  return (
    <ol className="relative ml-2 space-y-4 border-l border-line pl-5">
      {steps.map((step) => (
        <li key={step.id} className="relative">
          <span
            aria-hidden
            className={`absolute -left-[29px] top-0 flex h-4 w-4 items-center justify-center rounded-full border-2 border-panel text-white ${
              step.status === "done"
                ? "bg-ok"
                : step.status === "active"
                  ? "bg-primary"
                  : "bg-elev text-ink-low"
            }`}
          >
            {step.status === "done" ? (
              <Check size={9} />
            ) : step.status === "active" ? (
              <Loader2 size={9} className="animate-spin" />
            ) : (
              <CircleDashed size={9} />
            )}
          </span>
          <div
            className={`text-[13px] font-semibold ${
              step.status === "pending" ? "text-ink-low" : "text-ink-hi"
            }`}
          >
            {step.label}
          </div>
          {step.timestamp && (
            <div className="tabular text-2xs text-ink-low">{step.timestamp}</div>
          )}
          {step.note && (
            <div
              className={`mt-0.5 inline-block rounded-control px-1.5 py-0.5 text-2xs ${
                step.status === "active"
                  ? "bg-primary-soft text-primary"
                  : "bg-elev text-ink-mid"
              }`}
            >
              {step.note}
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}
