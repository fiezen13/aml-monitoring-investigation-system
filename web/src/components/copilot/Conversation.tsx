import { motion } from "motion/react";
import { ArrowDown, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { ApiCopilotAction } from "../../api/client";
import { transitions, useReduced } from "../../design/motion";

/**
 * Khung hội thoại: danh sách lượt, cuộn, và các kiểu tin nhắn.
 *
 * Quyết định trình bày quan trọng nhất ở đây là KHÔNG đóng khung mọi thứ. Câu
 * trả lời của trợ lý là chữ đặt thẳng trên nền panel; chỉ dữ liệu có cấu trúc
 * (đề xuất, biên nhận) mới được làm thẻ. Bọc mọi câu trong một bong bóng khiến
 * thẻ hành động — thứ duy nhất cần được chú ý — chìm lẫn vào đám bong bóng.
 */

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  action?: ApiCopilotAction | null;
}

export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[78%] rounded-panel border border-accent-line bg-accent-soft px-3.5 py-2 text-body leading-relaxed text-ink-hi">
        {text}
      </div>
    </div>
  );
}

export function AssistantMessage({ text }: { text: string }) {
  return (
    <div className="flex gap-2.5">
      <Sparkles size={13} className="mt-1 flex-none text-primary" aria-hidden />
      <p className="min-w-0 whitespace-pre-wrap text-body leading-relaxed text-ink-mid">{text}</p>
    </div>
  );
}

export function ThinkingRow() {
  return (
    <div className="flex items-center gap-2.5 text-body text-ink-low">
      <Sparkles size={13} className="flex-none animate-pulse text-primary" aria-hidden />
      Đang kiểm tra hàng đợi…
    </div>
  );
}

/** Bọc mỗi lượt bằng một chuyển động rất nhẹ — 4px, không trượt cả màn hình. */
export function MessageRow({ children }: { children: React.ReactNode }) {
  const reduced = useReduced();
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? { duration: 0.01 } : transitions.enter}
      className="space-y-3"
    >
      {children}
    </motion.div>
  );
}

/**
 * Vùng cuộn của hội thoại.
 *
 * Tự cuộn xuống khi có lượt mới, NHƯNG chỉ khi người dùng đang ở gần đáy. Đang
 * đọc lại một đề xuất cũ mà màn hình giật xuống là mất chỗ đang đọc; thay vào
 * đó hiện một nút nổi để họ tự quyết định lúc nào xuống.
 */
export function ConversationScroll({
  children,
  deps,
}: {
  children: React.ReactNode;
  /** Đổi giá trị này nghĩa là có nội dung mới. */
  deps: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [unread, setUnread] = useState(false);

  const scrollToBottom = () => {
    const el = ref.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setUnread(false);
  };

  useEffect(() => {
    if (atBottom) {
      const el = ref.current;
      if (el) el.scrollTop = el.scrollHeight;
    } else {
      setUnread(true);
    }
    // `atBottom` cố ý KHÔNG nằm trong deps: chỉ nội dung mới mới được kích hoạt
    // cuộn, chứ không phải mỗi lần người dùng cuộn tay một chút.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deps]);

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={ref}
        onScroll={(e) => {
          const el = e.currentTarget;
          const bottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
          setAtBottom(bottom);
          if (bottom) setUnread(false);
        }}
        className="copilot-scroll h-full overflow-y-auto px-5 py-4"
      >
        <div className="space-y-5">{children}</div>
      </div>

      {unread && (
        <button
          type="button"
          onClick={scrollToBottom}
          className="absolute bottom-3 left-1/2 flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-line-emphasis bg-raised px-3 py-1.5 text-data font-medium text-ink-hi shadow-popover transition-colors hover:border-primary/50"
        >
          <ArrowDown size={12} aria-hidden />
          Tin nhắn mới
        </button>
      )}
    </div>
  );
}
