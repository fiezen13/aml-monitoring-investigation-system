import { BrainCircuit, Crosshair, ShieldCheck } from "lucide-react";

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "Bảo mật đa tầng",
    body: "Giám sát truy cập, bảo vệ dữ liệu và duy trì khả năng kiểm toán.",
  },
  {
    icon: BrainCircuit,
    title: "AI Copilot tích hợp",
    body: "Hỗ trợ phân tích tín hiệu, bằng chứng và quá trình điều tra.",
  },
  {
    icon: Crosshair,
    title: "Điều tra theo bằng chứng",
    body: "Truy vết dòng tiền và quan hệ trên dữ liệu có nguồn gốc rõ ràng.",
  },
] as const;

/**
 * Ba thẻ năng lực.
 *
 * Câu mô tả cố ý nói về *việc hệ thống làm*, không phải lợi ích bán hàng —
 * đây là màn đăng nhập nội bộ, người đọc đã là người dùng rồi.
 */
export function LoginFeatureCards() {
  return (
    <div className="grid max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-3">
      {FEATURES.map(({ icon: Icon, title, body }, i) => (
        <div
          key={title}
          className="group animate-up rounded-panel border border-line bg-side/55 p-3 backdrop-blur-[2px] transition-[transform,border-color,background-color] duration-200 hover:-translate-y-0.5 hover:border-primary-line hover:bg-side/75"
          style={{ animationDelay: `${240 + i * 60}ms`, animationFillMode: "backwards" }}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-control border border-primary-line bg-primary-soft text-primary transition-colors group-hover:bg-primary/20">
            <Icon size={16} aria-hidden />
          </span>
          <div className="mt-2.5 text-[13px] font-semibold leading-snug text-ink-hi">{title}</div>
          <p className="mt-1 text-2xs leading-relaxed text-ink-low">{body}</p>
        </div>
      ))}
    </div>
  );
}
