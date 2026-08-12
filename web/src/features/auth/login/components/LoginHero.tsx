import { Suspense, lazy } from "react";

import { useReducedMotion, useSceneSize } from "../hooks/useReducedLoginEffects";
import { IntelligenceMetrics } from "./IntelligenceMetrics";
import { LoginBrand } from "./LoginBrand";
import { LoginFeatureCards } from "./LoginFeatureCards";
import { SystemStatusBar } from "./SystemStatusBar";

// Tách khỏi bundle chính: form phải hiện ngay, quả cầu đến sau cũng được.
const LoginNetworkScene = lazy(() =>
  import("./LoginNetworkScene").then((m) => ({ default: m.LoginNetworkScene })),
);

/**
 * Cột trái — vùng nhận diện và bối cảnh.
 *
 * Quả cầu nằm *dưới* chữ và tràn khỏi mép trái màn hình, không đứng cạnh chữ.
 * Nhờ vậy nó lấp đầy khoảng trống mà bản cũ bỏ phí, nhưng vẫn là nền: mắt đọc
 * tiêu đề trước, thấy quả cầu sau, và không có gì tranh chỗ với thẻ đăng nhập.
 */
export function LoginHero() {
  const reducedMotion = useReducedMotion();
  const sceneSize = useSceneSize();

  return (
    <div className="relative flex min-h-0 flex-1 flex-col justify-between overflow-hidden px-8 py-7 xl:px-12 xl:py-9">
      {/* Lớp nền: quả cầu neo về mép trái, cố ý bị cắt một phần. */}
      <div
        className="pointer-events-none absolute -left-[8%] top-1/2 -translate-y-1/2 opacity-95"
        aria-hidden
      >
        <Suspense fallback={<div style={{ width: sceneSize, height: sceneSize }} />}>
          <LoginNetworkScene size={sceneSize} reducedMotion={reducedMotion} />
        </Suspense>
      </div>

      <div className="relative z-[1]">
        <LoginBrand />
      </div>

      {/* Màn che dọc: quả cầu sáng nhất ở giữa, đúng chỗ tiêu đề nằm. Không có
          lớp này thì chữ đọc trên nền lưới lấp lánh và mất tương phản. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-[54%]"
        style={{ background: "linear-gradient(90deg, rgba(3,10,17,0.62) 0%, rgba(3,10,17,0.22) 52%, transparent 100%)" }}
      />

      <div className="relative z-[1] my-6 flex flex-col gap-5">
        <div>
          <h1
            className="animate-up max-w-[620px] text-[38px] font-bold leading-[1.08] tracking-tight text-ink-hi xl:text-[50px] 2xl:text-[56px]"
            style={{ animationDelay: "80ms", animationFillMode: "backwards" }}
          >
            Hệ thống giám sát và điều tra <span className="text-primary">AML</span> thế hệ mới
          </h1>
          <p
            className="animate-up mt-4 max-w-[520px] text-md leading-relaxed text-ink-mid"
            style={{ animationDelay: "160ms", animationFillMode: "backwards" }}
          >
            Phân tích dòng tiền, nhận diện rủi ro và hỗ trợ điều tra các hành vi tài chính bất thường trên dữ liệu có
            nguồn gốc rõ ràng.
          </p>
        </div>

        <LoginFeatureCards />
      </div>

      <div className="relative z-[1] flex flex-col gap-3">
        <IntelligenceMetrics />
        <SystemStatusBar />
      </div>
    </div>
  );
}
