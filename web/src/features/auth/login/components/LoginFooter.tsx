/**
 * Chân trang.
 *
 * Ghi rõ đây là môi trường mô phỏng. Số ở màn đăng nhập không thể là số thật —
 * trang này chạy trước khi xác thực nên không có quyền đọc gì — và một hệ thống
 * AML thì không được để người dùng nhầm lẫn giữa số minh hoạ và số vận hành.
 */
export function LoginFooter() {
  return (
    <footer className="fc-shell-auth flex flex-none flex-wrap items-center gap-x-3 gap-y-1 border-t border-line-faint py-4 text-3xs text-ink-dim">
      <span>Số liệu minh hoạ từ môi trường mô phỏng</span>
      <span className="h-2.5 w-px bg-line-strong" aria-hidden />
      <span>Môi trường: POC</span>
      <span className="ml-auto">© 2026 Velrix Financial Tech</span>
    </footer>
  );
}
