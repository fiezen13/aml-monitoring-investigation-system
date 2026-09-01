import { ShieldCheck } from "lucide-react";

/**
 * Khối nhận diện FIN-07.
 *
 * Ô logo dùng nền surface chứ không phải nền teal: teal trên màn này chỉ dành
 * cho nút truy cập và chỉ báo đang sống. Một logo phát sáng ở góc trên cùng
 * cạnh tranh trực tiếp với nút hành động — mà nút mới là thứ người dùng cần
 * tìm thấy đầu tiên.
 */
export function LoginBrand() {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-10 w-10 flex-none items-center justify-center rounded-control border border-line-strong bg-panel text-ink-mid">
        <ShieldCheck size={19} strokeWidth={1.7} aria-hidden />
      </span>
      <div className="min-w-0">
        <div className="text-xl font-semibold tracking-tight text-ink-hi">
          FIN-07 Bảng điều khiển AML
        </div>
        <div className="fc-eyebrow mt-0.5">Mạng lưới tình báo tài chính</div>
      </div>
    </div>
  );
}
