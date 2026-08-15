/**
 * Vai trò chữ.
 *
 * Trước đây có hơn 80 chỗ viết thẳng cỡ chữ tuỳ ý vào JSX (13px, 18px, 20px,
 * 9.5px…), nên thang chữ trên thực tế là "bất kỳ số nào người viết nghĩ ra lúc
 * đó". Bảng này đặt tên cho từng vai trò; JSX dùng tên, không dùng số.
 *
 * Font đơn cách chỉ dành cho dữ liệu cần thẳng cột hoặc cần đọc từng ký tự:
 * mã giao dịch, hash, ví, IP, số tiền, điểm rủi ro, dấu thời gian, chỉ số kỹ
 * thuật. Không dùng mono cho câu văn.
 */

export const TEXT = {
  /** Tiêu đề màn hình — 24px. Mỗi trang có tối đa một. */
  h1: "text-h1 font-semibold tracking-[-0.01em] text-ink-hi",
  /** Tiêu đề khối lớn — 20px. */
  h2: "text-h2 font-semibold tracking-[-0.005em] text-ink-hi",
  /** Tiêu đề panel — 16px. */
  h3: "text-h3 font-semibold text-ink-hi",
  /** Nội dung chính — 13px. */
  body: "text-body text-ink-mid",
  /** Nội dung cần nhấn — 14px. */
  bodyLg: "text-body-lg text-ink-mid",
  /** Dữ liệu dày trong bảng — 12px. */
  data: "text-data text-ink-mid",
  /** Metadata, chú thích dưới số liệu — 11px. */
  meta: "text-meta text-ink-low",
  /** Nhãn nhóm viết hoa — 10px, giãn chữ. */
  eyebrow: "text-micro font-medium uppercase tracking-[0.12em] text-ink-dim",
  /** Nhãn cột trong bảng — 10px hoa, nhạt hơn eyebrow một bậc. */
  columnLabel: "text-micro font-semibold uppercase tracking-[0.08em] text-ink-low",
} as const;

/** Class cho ô số liệu: mono + tabular để chữ số không nhảy khi giá trị đổi. */
export const NUMERIC = "font-mono tabular";

/** Số liệu lớn trong thẻ KPI. */
export const METRIC_VALUE = `${NUMERIC} text-h1 font-semibold leading-none`;

/** Số liệu vừa trong ô thống kê của sidebar và inspector. */
export const METRIC_VALUE_SM = `${NUMERIC} text-h3 font-semibold leading-tight`;
