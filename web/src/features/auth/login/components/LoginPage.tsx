import { LoginHero } from "./LoginHero";
import { LoginPanel } from "./LoginPanel";

/**
 * Màn đăng nhập FIN-07.
 *
 * Bốn tầng chiều sâu, từ dưới lên: nền, lưới kỹ thuật cùng quầng sáng, quả cầu
 * mạng lưới, rồi giao diện. Mỗi tầng chỉ được phép nhạt hơn tầng trên nó — thẻ
 * đăng nhập luôn là thứ tương phản cao nhất.
 */
export function LoginPage() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-[#030A11]">
      {/* Tầng 1 — quầng sáng. Hai nguồn rất nhạt, không phải ảnh nền. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(1100px 760px at 12% 48%, rgba(18,214,197,0.10), transparent 62%)," +
            "radial-gradient(900px 620px at 78% 18%, rgba(49,133,255,0.075), transparent 66%)",
        }}
      />

      {/* Tầng 2 — lưới kỹ thuật. Giữ ở mức gần như không thấy: nhìn ra được ô
          lưới là lập tức thành giao diện khoa học viễn tưởng. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(133,173,209,1) 1px, transparent 1px)," +
            "linear-gradient(90deg, rgba(133,173,209,1) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
        }}
      />

      {/* Tối bốn góc để mắt tự dồn vào giữa và sang phải. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(120% 90% at 50% 50%, transparent 42%, rgba(2,7,12,0.72) 100%)" }}
      />

      <div className="relative flex min-h-screen flex-col lg:flex-row">
        {/* Cột trái ẩn hẳn dưới lg: trên màn hẹp, thứ duy nhất người dùng cần
            là đăng nhập được, và quả cầu thì không nên tải về làm gì. */}
        <div className="hidden min-w-0 flex-1 lg:flex">
          <LoginHero />
        </div>
        <LoginPanel />
      </div>
    </div>
  );
}
