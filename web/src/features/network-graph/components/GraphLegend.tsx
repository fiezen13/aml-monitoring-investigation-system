import { C } from "../../../design/palette";

const ENTITIES: [string, string][] = [
  ["Cá nhân", C.info],
  ["Tổ chức", C.agent],
  ["Tài khoản", C.primary],
  ["Thiết bị", C.inkLow],
  ["Ví", C.ok],
  ["Nền tảng", C.inkSoft],
];

/**
 * Chú giải nổi ở góc dưới trái.
 *
 * Gọn lại thành hai hàng sát nhau: bản trước trải gần hết chiều ngang đáy
 * canvas và ăn mất một dải đồ thị. Kiểu nét vẫn phải giải thích vì nét liền /
 * đứt / chấm mang ba mức chắc chắn khác nhau của bằng chứng — đó là phân biệt
 * quan trọng nhất trên màn hình này.
 */
export function GraphLegend() {
  return (
    <div className="pointer-events-none absolute bottom-2.5 left-2.5 z-[5] rounded-control border border-line bg-side/85 px-2.5 py-1.5 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5">
        {ENTITIES.map(([label, color]) => (
          <span key={label} className="flex items-center gap-1 text-3xs text-ink-low">
            <span className="h-1.5 w-1.5 rounded-sm" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
      {/* Ba mức chắc chắn của bằng chứng phải phân biệt được ngay ở chú giải:
          quan sát trực tiếp, mô hình suy ra, và chỗ chưa chứng minh được. */}
      <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-0.5 border-t border-line-faint pt-1">
        <LineKey label="quan sát" dash="none" color={C.primary} />
        <LineKey label="suy luận" dash="5,4" color={C.agent} />
        <LineKey label="thiếu liên kết" dash="1,4" color={C.inkSoft} gap />
        <LineKey label="đường tiền chính" dash="none" color={C.risk} />
        {/* Hai màu này chỉ bật khi có đỉnh được chọn — chúng trả lời câu hỏi đầu
            tiên của chuyên viên: tiền vào hay tiền ra khỏi tài khoản đang xem. */}
        <LineKey label="tiền vào (khi chọn 1 tài khoản)" dash="none" color={C.ok} />
        <LineKey label="tiền ra" dash="none" color={C.warn} />
        <span className="flex items-center gap-1 text-3xs text-ink-low">
          <span
            className="flex h-2.5 w-2.5 items-center justify-center rounded-full text-[6px]"
            style={{ background: C.ok, color: C.app }}
          >
            ✓
          </span>
          đối chứng đã soát
        </span>
      </div>
    </div>
  );
}

function LineKey({
  label,
  dash,
  color,
  gap = false,
}: {
  label: string;
  dash: string;
  color: string;
  /** Kèm dấu hỏi — dấu hiệu riêng của chỗ thiếu liên kết quan sát. */
  gap?: boolean;
}) {
  return (
    <span className="flex items-center gap-1 text-3xs text-ink-low">
      <svg width={gap ? 20 : 16} height="7" aria-hidden="true">
        <line
          x1="0"
          y1="3.5"
          x2={gap ? 20 : 16}
          y2="3.5"
          stroke={color}
          strokeWidth="1.8"
          strokeDasharray={dash === "none" ? undefined : dash}
        />
        {gap && (
          <>
            <circle cx="10" cy="3.5" r="3.4" fill={C.app} stroke={color} strokeWidth="0.9" />
            <text x="10" y="6" fontSize="5" textAnchor="middle" fill={color}>
              ?
            </text>
          </>
        )}
      </svg>
      {label}
    </span>
  );
}
