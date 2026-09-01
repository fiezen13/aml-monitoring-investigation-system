import { LoginFooter } from "./LoginFooter";
import { LoginHero } from "./LoginHero";
import { LoginPanel } from "./LoginPanel";
import { LoginTopBar } from "./LoginTopBar";

/**
 * Màn đăng nhập FIN-07.
 *
 * Bố cục là một khung căn giữa (`fc-shell`, tối đa 1440px) chứ không phải hai
 * cột dàn ra hai mép viewport. Bản cũ để hero `flex-1` và panel `38vw` bám sát
 * hai bên: ở 1920px, chữ nằm ở x=48 còn form ở x=1449, chừa lại 700px trống ở
 * giữa mà không có nội dung nào giải thích. Màn càng rộng thì khoảng trống ấy
 * càng phình. Khung căn giữa xử lý tận gốc: hai cột luôn nằm cạnh nhau, phần
 * thừa đẩy ra hai lề — trở thành lề có chủ ý thay vì lỗ hổng ở giữa.
 *
 * Dưới 1024px chuyển về một cột và thẻ đăng nhập lên trước: người mở trang
 * trên màn hẹp đến đây để đăng nhập, không phải để đọc giới thiệu.
 */
export function LoginPage() {
  return (
    <div className="relative min-h-screen overflow-hidden bg-app">
      {/* Tầng 1 — quầng sáng. Hai nguồn rất nhạt, không phải ảnh nền. Đặt lệch
          về nửa trái để đỡ phần hero, không phủ lên thẻ đăng nhập. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(1000px 720px at 22% 46%, rgba(32,199,167,0.07), transparent 62%)," +
            "radial-gradient(900px 620px at 72% 14%, rgba(75,158,255,0.05), transparent 66%)",
        }}
      />

      {/* Tầng 2 — lưới kỹ thuật. Giữ ở mức gần như không thấy: nhìn ra được ô
          lưới là lập tức thành giao diện khoa học viễn tưởng. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(133,173,209,1) 1px, transparent 1px)," +
            "linear-gradient(90deg, rgba(133,173,209,1) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />

      {/* Tối bốn góc để mắt dồn vào khối nội dung ở giữa. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{ background: "radial-gradient(120% 92% at 50% 48%, transparent 46%, rgba(4,8,12,0.7) 100%)" }}
      />

      <div className="fc-auth-page relative flex min-h-screen flex-col">
        <LoginTopBar />

        <main className="fc-shell-auth flex flex-1 items-center py-8 lg:py-10">
          <div className="grid w-full gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_400px] lg:items-center xl:grid-cols-[minmax(0,1fr)_440px] xl:gap-x-16">
            {/* Thẻ đăng nhập đứng trước trong DOM ở màn hẹp; từ lg trở lên
                grid trả nó về cột phải. */}
            <div className="order-2 min-w-0 lg:order-1">
              <LoginHero />
            </div>
            <div className="order-1 flex min-w-0 justify-center lg:order-2">
              <LoginPanel />
            </div>
          </div>
        </main>

        <LoginFooter />
      </div>
    </div>
  );
}
