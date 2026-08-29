import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { priorityLabel } from "../../api/format";
import { Tooltip } from "../ui/Overlay";

/**
 * Những mảnh nhỏ dùng chung của trợ lý điều phối.
 *
 * Tách ra vì chúng lặp ở cả thẻ đề xuất lẫn biên nhận, và vì mỗi mảnh mang một
 * quyết định trình bày riêng đáng được nói rõ ở chỗ nó sống.
 */

/**
 * Mã hồ sơ, rút gọn cho người đọc.
 *
 * Mã thật dài 33 ký tự (`CASE-AUTO-a8f288850ec77e9b3324430e`). Để nguyên thì nó
 * thành khối chữ to nhất trong thẻ — mắt bị kéo vào một chuỗi băm thay vì vào
 * mức rủi ro và người nhận, và giao diện nghiệp vụ trông như bảng điều khiển
 * của lập trình viên.
 *
 * Rút gọn phần giữa, giữ đủ đuôi để phân biệt hai hồ sơ cạnh nhau. Mã đầy đủ
 * KHÔNG mất: hiện ở tooltip, sao chép được bằng một nút, và mở được hồ sơ.
 */
export function CaseId({ id, onOpen }: { id: string; onOpen?: (id: string) => void }) {
  const [copied, setCopied] = useState(false);
  // Tách ở dấu gạch CUỐI CÙNG, không giả định tiền tố.
  //
  // Bản đầu chỉ biết "CASE-AUTO-", nên `CASE-544e2a92dcac4a4aa49c` bị cắt thành
  // `CASE-544e2a92dcac4a4aa49c…AA49C` — dài hơn cả mã gốc. Hệ thống có ít nhất
  // hai dạng mã, và sẽ còn dạng khác.
  const cut = id.lastIndexOf("-");
  const head = cut > 0 ? id.slice(0, cut) : id;
  const hash = cut > 0 ? id.slice(cut + 1) : "";
  const tail = hash.slice(-5).toUpperCase();
  // Đuôi ngắn thì rút gọn chẳng lợi gì — hiện nguyên cho khỏi thêm dấu ba chấm.
  const shortened = hash.length > 8;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      /* trình duyệt chặn clipboard — tooltip vẫn cho đọc mã đầy đủ */
    }
  };

  return (
    <span className="inline-flex items-center gap-1">
      <Tooltip label={id}>
        <button
          type="button"
          onClick={() => onOpen?.(id)}
          disabled={!onOpen}
          title={id}
          className="tabular rounded-control text-body font-medium text-info transition-colors hover:text-info-soft focus:outline-none focus-visible:ring-1 focus-visible:ring-info disabled:cursor-default disabled:hover:text-info"
        >
          {shortened ? `${head}…${tail}` : id}
        </button>
      </Tooltip>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={`Sao chép mã hồ sơ ${id}`}
        className="rounded-control p-0.5 text-ink-dim opacity-0 transition-opacity hover:text-ink-mid focus:outline-none focus-visible:opacity-100 focus-visible:ring-1 focus-visible:ring-line-emphasis group-hover/case:opacity-100"
      >
        {copied ? <Check size={11} aria-hidden /> : <Copy size={11} aria-hidden />}
      </button>
    </span>
  );
}

/** Điểm rủi ro — số trần, đủ để so hàng nào cao hơn hàng nào. */
export function RiskScore({ score }: { score: number }) {
  return <span className="tabular text-body font-semibold text-ink-hi">{Math.round(score)}</span>;
}

/**
 * Mức ưu tiên. Chỉ một chấm màu và một chữ nhỏ.
 *
 * "Nghiêm trọng" tô đỏ đậm cả dòng thì mọi hàng đều đỏ (phần lớn hàng đợi ở mức
 * critical) và màu mất hết khả năng phân biệt.
 */
const PRIORITY_DOT: Record<string, string> = {
  critical: "bg-risk",
  high: "bg-warn",
  medium: "bg-info",
  low: "bg-ink-dim",
};

export function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-data text-ink-mid">
      <span
        className={`h-1.5 w-1.5 flex-none rounded-full ${PRIORITY_DOT[priority] ?? "bg-ink-dim"}`}
        aria-hidden
      />
      {priorityLabel(priority)}
    </span>
  );
}

/** Nhãn của một khối trong thẻ. Nhỏ, không in hoa toàn bộ. */
export function FieldLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-meta font-semibold tracking-[0.04em] text-ink-low">{children}</div>;
}

/** Chữ viết tắt tên, dùng khi hệ thống không có ảnh đại diện. */
export function Initials({ name }: { name: string }) {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(-3)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
  return (
    <span
      className="grid h-7 w-7 flex-none place-items-center rounded-full border border-line bg-elev text-meta font-semibold text-ink-mid"
      aria-hidden
    >
      {letters || "?"}
    </span>
  );
}
