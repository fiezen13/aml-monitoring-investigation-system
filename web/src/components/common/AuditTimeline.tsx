import { AUDIT_ACTION_LABEL } from "../../data/mockAudit";
import type { AuditEvent } from "../../types";
import { StatusBadge } from "./Badges";

/**
 * Dòng thời gian audit — chỉ đọc (NT4): component này không render
 * bất kỳ nút sửa hoặc xóa nào.
 */
export function AuditTimeline({ events }: { events: AuditEvent[] }) {
  return (
    <ol className="relative ml-2 space-y-4 border-l border-line pl-5">
      {events.map((event) => (
        <li key={event.id} className="relative">
          <span
            aria-hidden
            className={`absolute -left-[26px] top-1 h-2.5 w-2.5 rounded-full border-2 border-panel ${
              event.action.includes("denied") || event.action.includes("locked")
                ? "bg-risk"
                : event.actorRole === "system" || event.actorRole === "agent"
                  ? "bg-info"
                  : "bg-primary"
            }`}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13px] font-semibold text-ink-hi">
              {AUDIT_ACTION_LABEL[event.action] ?? event.action}
            </span>
            <span className="tabular text-2xs text-ink-low">{event.time}</span>
            <span className="tabular text-2xs text-ink-low">IP {event.ip}</span>
          </div>
          <div className="mt-0.5 text-2xs text-ink-mid">
            <span className="font-medium text-ink-hi">{event.actor}</span>
            {" · "}
            {event.actorRole}
            {" → "}
            <span className="tabular">{event.target}</span>
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-ink-mid">{event.detail}</p>
          {(event.stateBefore || event.stateAfter) && (
            <div className="mt-1.5 flex items-center gap-1.5">
              {event.stateBefore && <StatusBadge tone="muted" label={event.stateBefore} />}
              {event.stateBefore && event.stateAfter && (
                <span className="text-ink-low" aria-hidden>
                  →
                </span>
              )}
              {event.stateAfter && <StatusBadge tone="primary" label={event.stateAfter} />}
            </div>
          )}
          {event.reason && (
            <p className="mt-1.5 rounded-control border border-line bg-elev px-2.5 py-1.5 text-2xs italic text-ink-mid">
              Lý do: "{event.reason}"
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}
