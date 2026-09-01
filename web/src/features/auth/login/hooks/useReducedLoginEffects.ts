import { useEffect, useState } from "react";

/**
 * Người dùng có yêu cầu giảm chuyển động không.
 *
 * Theo dõi cả thay đổi trong lúc đang mở trang chứ không chỉ đọc một lần: đổi
 * cài đặt hệ thống mà giao diện không phản ứng thì coi như không hỗ trợ.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduced;
}

/**
 * Cỡ cạnh của quả cầu, bám theo bề rộng cửa sổ.
 *
 * Ở 1366×768 quả cầu phải nhỏ lại đáng kể, nếu không cột trái đội cao lên và
 * thẻ đăng nhập bị đẩy khỏi màn hình — mà thẻ đăng nhập mới là thứ người dùng
 * đến đây để dùng.
 */
export function useSceneSize(): number {
  const [size, setSize] = useState(() => sceneSizeFor(typeof window === "undefined" ? 1920 : window.innerWidth));

  useEffect(() => {
    let frame = 0;
    const onResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setSize(sceneSizeFor(window.innerWidth)));
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("resize", onResize);
    };
  }, []);

  return size;
}

/**
 * Quả cầu phải *lớn*. Bán kính vẽ chỉ bằng 0.31 cạnh khung, phần còn lại là
 * quầng sáng và vành đai, nên một khung 900px mới cho ra quả cầu đường kính
 * khoảng 560px — đủ để lấp vùng trống của cột trái. Khung nhỏ hơn thì nó co
 * lại thành một chấm sáng ở góc và cột trái trông như bỏ hoang.
 */
function sceneSizeFor(width: number): number {
  if (width >= 1800) return 900;
  if (width >= 1600) return 780;
  if (width >= 1440) return 660;
  if (width >= 1280) return 560;
  return 460;
}
