import { Suspense, lazy } from "react";

import { useReducedMotion, useSceneSize } from "../hooks/useReducedLoginEffects";
import { IntelligenceMetrics } from "./IntelligenceMetrics";
import { LoginFeatureCards } from "./LoginFeatureCards";

// Tách khỏi bundle chính: form phải hiện ngay, quả cầu đến sau cũng được.
const LoginNetworkScene = lazy(() =>
  import("./LoginNetworkScene").then((m) => ({ default: m.LoginNetworkScene })),
);

/**
 * Cột trái — nhận diện và bối cảnh.
 *
 * Phân cấp: eyebrow → tiêu đề → đoạn dẫn → dải năng lực → dải số liệu. Bốn khối
 * cách nhau bằng khoảng trắng và một đường kẻ mảnh, không phải bằng bốn cái
 * hộp có viền — đây là chỗ bản cũ tạo ra cảm giác lưới ô vuông.
 *
 * Quả cầu nằm *dưới* chữ và tràn khỏi mép trái, không đứng cạnh chữ: nó là nền,
 * không phải một cột nội dung. Ẩn hẳn dưới 1024px, nơi trang chỉ còn một cột và
 * thứ duy nhất người dùng cần là đăng nhập được.
 */
export function LoginHero() {
  const reducedMotion = useReducedMotion();
  const sceneSize = useSceneSize();

  return (
    <div className="relative">
      <div
        className="pointer-events-none absolute -left-[26%] top-1/2 hidden -translate-y-1/2 opacity-70 lg:block"
        aria-hidden
      >
        <Suspense fallback={<div style={{ width: sceneSize, height: sceneSize }} />}>
          <LoginNetworkScene size={sceneSize} reducedMotion={reducedMotion} />
        </Suspense>
      </div>

      {/* Màn che dọc: quả cầu sáng nhất ở giữa, đúng chỗ tiêu đề nằm. Không có
          lớp này thì chữ đọc trên nền lưới lấp lánh và mất tương phản. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-y-16 -left-[30%] right-[18%] hidden lg:block"
        style={{
          background:
            "linear-gradient(90deg, rgba(8,13,18,0.78) 0%, rgba(8,13,18,0.42) 55%, transparent 100%)",
        }}
      />

      <div className="relative max-w-[740px]">
        <p
          className="animate-up fc-eyebrow"
          style={{ animationDelay: "60ms", animationFillMode: "backwards" }}
        >
          Nền tảng tình báo tài chính FIN-07
        </p>

        <h1
          className="animate-up mt-3 text-[32px] font-semibold leading-[1.06] tracking-[-0.02em] text-ink-hi sm:text-[38px] xl:text-[46px] 2xl:text-[50px]"
          style={{ animationDelay: "100ms", animationFillMode: "backwards" }}
        >
          Giám sát và điều tra rủi ro tài chính.
        </h1>

        <p
          className="animate-up mt-4 max-w-[560px] text-md leading-relaxed text-ink-soft"
          style={{ animationDelay: "160ms", animationFillMode: "backwards" }}
        >
          Phát hiện tín hiệu bất thường, truy vết dòng tiền và hỗ trợ điều tra trên dữ liệu có nguồn gốc rõ ràng.
        </p>

        <LoginFeatureCards />
        <IntelligenceMetrics />
      </div>
    </div>
  );
}
