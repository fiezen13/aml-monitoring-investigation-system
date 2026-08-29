import { AnimatePresence, motion } from "motion/react";
import { AlertTriangle, ChevronRight, CircleSlash, Check } from "lucide-react";
import { useState } from "react";

import type { ApiCopilotAction } from "../../api/client";
import { formatDateTime, priorityLabel } from "../../api/format";
import { transitions, useReduced } from "../../design/motion";
import { CaseList } from "./ActionProposalCard";
import { FieldLabel } from "./atoms";

/**
 * Biên nhận — thẻ SAU khi đề xuất đã có kết cục.
 *
 * Một thẻ đề xuất cao 300–400px là hợp lý khi người dùng còn phải quyết định.
 * Giữ nguyên chiều cao ấy sau khi đã bấm là đẩy toàn bộ hội thoại xuống dưới vì
 * một việc không còn phải làm gì nữa: sau ba lượt giao việc, màn hình chỉ còn
 * là ba khối chết.
 *
 * Nên kết cục thu về một dòng. Chi tiết KHÔNG mất — bấm "Xem chi tiết" là mở
 * lại đủ, và dữ liệu kiểm toán ở máy chủ vốn không đụng tới. Đây là thu gọn ở
 * lớp TRÌNH BÀY, không phải bỏ bớt dữ liệu.
 */

type Status = "done" | "cancelled" | "failed";

const TONE: Record<Status, { ring: string; text: string; icon: typeof Check }> = {
  done: { ring: "border-ok/30 bg-ok/[0.06]", text: "text-ok", icon: Check },
  cancelled: { ring: "border-line bg-elev/60", text: "text-ink-mid", icon: CircleSlash },
  failed: { ring: "border-warn/40 bg-warn/[0.07]", text: "text-warn", icon: AlertTriangle },
};

export function ActionReceipt({
  action,
  status,
  message,
  at,
  actor,
}: {
  action: ApiCopilotAction;
  status: Status;
  message?: string;
  /** Thời điểm có kết cục; bỏ trống thì không hiện, không đoán. */
  at?: string;
  actor?: string;
}) {
  const [open, setOpen] = useState(false);
  const reduced = useReduced();
  const tone = TONE[status];
  const Icon = tone.icon;
  const meta = [at ? formatDateTime(at) : null, actor ? `bởi ${actor}` : null].filter(Boolean).join(" · ");

  return (
    <section className={`rounded-panel border ${tone.ring}`}>
      <div className="flex items-start gap-2.5 px-4 py-2.5">
        <Icon size={14} className={`mt-0.5 flex-none ${tone.text}`} aria-hidden />
        <div className="min-w-0 flex-1">
          <div className={`text-body font-medium ${status === "done" ? "text-ink-hi" : tone.text}`}>
            {message}
          </div>
          {meta && <div className="mt-0.5 text-data text-ink-dim">{meta}</div>}
        </div>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex flex-none items-center gap-0.5 rounded-control px-1.5 py-0.5 text-data text-ink-low transition-colors hover:text-ink-hi focus:outline-none focus-visible:ring-1 focus-visible:ring-line-emphasis"
        >
          {open ? "Thu gọn" : "Xem chi tiết"}
          <ChevronRight
            size={12}
            aria-hidden
            className={`transition-transform ${open ? "rotate-90" : ""}`}
          />
        </button>
      </div>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={reduced ? false : { height: 0, opacity: 0 }}
            animate={reduced ? {} : { height: "auto", opacity: 1 }}
            exit={reduced ? {} : { height: 0, opacity: 0 }}
            transition={reduced ? { duration: 0.01 } : transitions.state}
            className="overflow-hidden"
          >
            <div className="space-y-3 border-t border-line-faint px-4 py-3">
              {action.assignee_display_name && (
                <div>
                  <FieldLabel>Người nhận</FieldLabel>
                  <div className="mt-0.5 text-body text-ink-hi">{action.assignee_display_name}</div>
                </div>
              )}
              <div>
                <FieldLabel>Hồ sơ</FieldLabel>
                <div className="mt-0.5">
                  <CaseList cases={action.cases} />
                </div>
              </div>
              {action.due_at && (
                <div>
                  <FieldLabel>Hạn xử lý</FieldLabel>
                  <div className="tabular mt-0.5 text-body text-ink-hi">{formatDateTime(action.due_at)}</div>
                </div>
              )}
              {action.priority && (
                <div>
                  <FieldLabel>Mức ưu tiên</FieldLabel>
                  <div className="mt-0.5 text-body text-ink-hi">{priorityLabel(action.priority)}</div>
                </div>
              )}
              {action.instruction && (
                <div>
                  <FieldLabel>Chỉ dẫn</FieldLabel>
                  <p className="mt-0.5 text-body leading-relaxed text-ink-mid">{action.instruction}</p>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
