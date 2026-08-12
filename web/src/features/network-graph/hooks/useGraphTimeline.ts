import { useEffect } from "react";

/**
 * Chạy thanh thời gian.
 *
 * Chỉ đẩy `timeT` lên dần; việc ẩn/hiện do bộ lọc lo. Điểm mấu chốt là *không*
 * dựng lại đồ thị: node chưa tồn tại ở mốc đang xem bị lọc ra khỏi render
 * graph, còn toạ độ layout giữ nguyên nên đồ thị không nhảy khi kéo.
 */
export function useGraphTimeline(
  playing: boolean,
  timeT: number,
  setTimeT: (v: number) => void,
  stop: () => void,
): void {
  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    let last = performance.now();

    const tick = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      // Chạy hết dải trong khoảng 12 giây — đủ chậm để thấy thứ tự xuất hiện.
      const next = timeTRef.value + dt / 12;
      if (next >= 1) {
        timeTRef.value = 1;
        setTimeT(1);
        stop();
        return;
      }
      timeTRef.value = next;
      setTimeT(next);
      raf = requestAnimationFrame(tick);
    };

    const timeTRef = { value: timeT >= 1 ? 0 : timeT };
    if (timeT >= 1) setTimeT(0);
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // `timeT` cố tình không nằm trong deps: nó đổi mỗi khung hình và đưa vào
    // đây sẽ huỷ rồi tạo lại vòng lặp liên tục.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);
}
