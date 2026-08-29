import { ArrowUp } from "lucide-react";
import { useEffect, useRef } from "react";

/**
 * Thanh nhập lệnh, dính đáy ngăn kéo.
 *
 * Trước đây là một `textarea` hai dòng cạnh một nút chữ "Gửi" — nút chiếm chỗ
 * bằng một phần tư chiều ngang cho một hành động ai cũng làm bằng phím Enter.
 * Nay: ô nhập tự cao dần theo nội dung (tối đa ~140px, quá đó thì cuộn trong
 * ô), nút gửi là một hình vuông 40px, và phím tắt được nói thẳng ra thay vì
 * giấu trong placeholder.
 */
export function CopilotComposer({
  value,
  onChange,
  onSend,
  sending,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  sending: boolean;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const empty = !value.trim();

  // Cao dần theo nội dung. Đặt lại về "auto" trước khi đo, nếu không chiều cao
  // chỉ tăng được chứ không bao giờ co lại khi người dùng xoá bớt chữ.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`;
  }, [value]);

  return (
    <div className="flex-none border-t border-line bg-side px-5 py-3.5">
      <div className="flex items-end gap-2 rounded-panel border border-line bg-panel px-3 py-2 transition-colors focus-within:border-line-emphasis">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          rows={1}
          aria-label="Câu hỏi hoặc yêu cầu điều phối"
          placeholder="Hỏi về hồ sơ hoặc giao việc cho chuyên viên…"
          className="max-h-[140px] min-h-[24px] flex-1 resize-none bg-transparent py-1 text-body leading-relaxed text-ink-hi placeholder:text-ink-dim focus:outline-none"
        />
        <button
          type="button"
          onClick={onSend}
          disabled={empty || sending}
          aria-label="Gửi"
          className="grid h-9 w-9 flex-none place-items-center rounded-control bg-primary text-app transition-colors hover:bg-primary-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/50 disabled:bg-elev disabled:text-ink-dim"
        >
          <ArrowUp size={15} aria-hidden />
        </button>
      </div>
      <div className="mt-1.5 px-1 text-micro text-ink-dim">
        <kbd className="font-sans">Enter</kbd> để gửi · <kbd className="font-sans">Shift + Enter</kbd> xuống
        dòng
      </div>
    </div>
  );
}
