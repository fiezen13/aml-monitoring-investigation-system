/**
 * Hàng trạng thái cuối cột trái.
 *
 * Ghi rõ đây là môi trường mô phỏng ngay cạnh khối số liệu phía trên. Số ở màn
 * đăng nhập không thể là số thật — trang này chạy trước khi xác thực nên không
 * có quyền đọc gì — và một hệ thống AML thì không được để người dùng nhầm lẫn
 * giữa số minh hoạ và số vận hành.
 */
export function SystemStatusBar() {
  return (
    <div
      className="animate-up flex flex-wrap items-center gap-x-3 gap-y-1 text-3xs text-ink-dim"
      style={{ animationDelay: "580ms", animationFillMode: "backwards" }}
    >
      <span className="inline-flex items-center gap-1.5 text-ok-soft">
        <span className="h-1.5 w-1.5 rounded-full bg-ok" aria-hidden />
        Tất cả hệ thống đang trực tuyến
      </span>
      <span className="h-2.5 w-px bg-line-strong" aria-hidden />
      <span>Số liệu minh hoạ từ môi trường mô phỏng</span>
      <span className="h-2.5 w-px bg-line-strong" aria-hidden />
      <span>© 2026 Velrix Financial Tech</span>
    </div>
  );
}
