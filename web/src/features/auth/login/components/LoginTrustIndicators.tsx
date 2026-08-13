import { KeyRound, ScrollText, Users } from "lucide-react";

/**
 * Ba chỉ dấu tin cậy.
 *
 * Cố ý *không* ghi TLS 1.3, AES-256 hay ISO 27001 như bản thiết kế tham chiếu.
 * Không có gì trong repo này chứng minh được ba điều đó, và một hệ thống tuân
 * thủ mà in chuẩn tuân thủ nó không đạt lên ngay màn đăng nhập thì hỏng ngay ở
 * câu đầu tiên.
 *
 * Ba mục dưới đây đều kiểm chứng được trong chính mã nguồn: bảng `audit_log`
 * cùng màn Audit trail, năm vai trò trong `Role` cùng màn hình từ chối truy
 * cập, và phiên lưu bằng `sessionStorage` nên đóng trình duyệt là mất.
 */
const ITEMS = [
  { icon: ScrollText, code: "AUDIT", label: "Nhật ký truy cập" },
  { icon: Users, code: "RBAC", label: "Phân quyền vai trò" },
  { icon: KeyRound, code: "SESSION", label: "Hết phiên khi đóng" },
] as const;

export function LoginTrustIndicators() {
  return (
    <div className="fc-auth-tight mt-4 grid grid-cols-3 gap-2 border-t border-line-faint pt-4">
      {ITEMS.map(({ icon: Icon, code, label }) => (
        <div key={code} className="flex items-center gap-2">
          <Icon size={13} strokeWidth={1.6} className="flex-none text-ink-dim" aria-hidden />
          <span className="min-w-0">
            <span className="block font-mono text-3xs font-semibold tracking-[0.06em] text-ink-soft">{code}</span>
            <span className="block truncate text-3xs text-ink-dim">{label}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
