/**
 * Đồng hồ dòng chảy dùng chung cho cả World.
 *
 * Ba lý do nó phải là một đối tượng duy nhất chứ không phải một hook trong mỗi
 * bộ dựng hình:
 *
 *  1. **Liên tục khi đổi phép chiếu.** Gói tiền đang ở 47% quãng đường trên bản
 *     đồ phẳng thì sau khi bấm sang quả cầu nó phải vẫn ở khoảng 47%. Hai đồng
 *     hồ riêng, mỗi cái bắt đầu từ 0 lúc component dựng, sẽ luôn cho hai vị trí
 *     khác nhau.
 *  2. **Một vòng lặp cho cả màn hình.** Hàng trăm hành lang, một
 *     `requestAnimationFrame`. Không có timer riêng cho từng hành lang.
 *  3. **Dừng khi không ai nhìn.** Tab ẩn thì ngừng cộng dồn — vừa đỡ tốn pin,
 *     vừa tránh cú nhảy vài phút khi người dùng quay lại.
 *
 * Thời gian được cộng dồn từ delta của `performance.now()` chứ không lấy hiệu
 * số với mốc khởi tạo: cách sau khiến mọi khoảng thời gian tab bị ẩn vẫn được
 * tính, và hành lang sẽ nhảy vọt khi quay lại.
 */

type Listener = (flowTime: number) => void;

/** Chặn delta bất thường: tab vừa hiện lại, hoặc trình duyệt vừa bị treo. */
const MAX_FRAME_SECONDS = 1 / 20;

class WorldFlowClock {
  private elapsed = 0;
  private lastFrame = 0;
  private frame = 0;
  private readonly listeners = new Set<Listener>();
  private paused = false;

  /** Thời gian dòng chảy, tính bằng giây. Đây là đầu vào duy nhất của shader. */
  get time(): number {
    return this.elapsed;
  }

  /**
   * Đăng ký một bộ dựng hình. Vòng lặp chỉ chạy khi có người nghe, nên rời khỏi
   * màn Giám sát địa lý là nó tự dừng.
   */
  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    this.start();
    return () => {
      this.listeners.delete(listener);
      if (this.listeners.size === 0) this.stop();
    };
  }

  private start(): void {
    if (this.frame || typeof window === "undefined") return;
    this.lastFrame = performance.now();
    this.frame = window.requestAnimationFrame(this.tick);
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  private stop(): void {
    if (this.frame) window.cancelAnimationFrame(this.frame);
    this.frame = 0;
    document.removeEventListener("visibilitychange", this.onVisibility);
  }

  private readonly onVisibility = (): void => {
    this.paused = document.hidden;
    // Bỏ luôn delta của khoảng thời gian bị ẩn: mốc được đặt lại ngay khi tab
    // hiện trở lại, nên khung hình đầu tiên sau đó có delta bình thường.
    this.lastFrame = performance.now();
  };

  private readonly tick = (now: number): void => {
    this.frame = window.requestAnimationFrame(this.tick);
    const delta = Math.min(MAX_FRAME_SECONDS, (now - this.lastFrame) / 1000);
    this.lastFrame = now;
    if (this.paused) return;
    this.elapsed += delta;
    for (const listener of this.listeners) listener(this.elapsed);
  };
}

/**
 * Một thể duy nhất cho toàn ứng dụng.
 *
 * Cố ý là module-level singleton chứ không phải React context: hai bộ dựng hình
 * đọc nó trong vòng lặp vẽ, không phải trong lượt render của React, và đưa nó
 * qua context chỉ tạo cảm giác an toàn giả trong khi thêm một tầng gián tiếp.
 */
export const worldFlowClock = new WorldFlowClock();
