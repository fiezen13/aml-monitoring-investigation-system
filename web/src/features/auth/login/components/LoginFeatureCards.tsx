import { BrainCircuit, Crosshair, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Bảo mật đa tầng",
    body: "Kiểm soát truy cập, phân quyền vai trò và nhật ký kiểm toán.",
  },
  {
    icon: BrainCircuit,
    title: "AI Copilot tích hợp",
    body: "Hỗ trợ phân tích tín hiệu và quá trình điều tra.",
  },
  {
    icon: Crosshair,
    title: "Điều tra theo bằng chứng",
    body: "Mọi kết luận truy ngược được về nguồn dữ liệu.",
  },
] as const;

/**
 * Ba năng lực chính.
 *
 * Là hàng nội dung, không phải thẻ có viền. Bản cũ bọc mỗi mục trong một hộp
 * `border + bg + backdrop-blur` nên ba mục thành ba khối nặng ngang nhau, cạnh
 * tranh với tiêu đề ngay phía trên. Ở đây chỉ còn một đường kẻ mảnh phân tách
 * cụm này với đoạn dẫn, còn phân cấp bên trong do cỡ chữ và màu lo.
 *
 * Câu mô tả cố ý nói về *việc hệ thống làm*, không phải lợi ích bán hàng — đây
 * là màn đăng nhập nội bộ, người đọc đã là người dùng rồi.
 */
export function LoginFeatureCards() {
  return (
    <div className="mt-8 grid gap-x-8 gap-y-5 border-t border-line-faint pt-6 sm:grid-cols-3">
      {FEATURES.map(({ icon: Icon, title, body }, i) => (
        <div
          key={title}
          className="animate-up min-w-0"
          style={{ animationDelay: `${220 + i * 60}ms`, animationFillMode: "backwards" }}
        >
          <Icon size={17} strokeWidth={1.6} className="text-ink-soft" aria-hidden />
          <div className="mt-2.5 text-md font-semibold leading-snug text-ink-hi">{title}</div>
          <p className="mt-1 text-2xs leading-relaxed text-ink-low">{body}</p>
        </div>
      ))}
    </div>
  );
}
