import { useEffect, useRef } from "react";

import { C } from "../../../../design/palette";
import type { SceneData } from "../utils/loginSceneData";
import { buildSceneData } from "../utils/loginSceneData";

interface Props {
  /** Cạnh của khung vẽ, px. Quả cầu chiếm khoảng 62% cạnh này. */
  size: number;
  /** Tắt mọi chuyển động — dựng một khung tĩnh rồi dừng. */
  reducedMotion: boolean;
}

/** Tốc độ xoay, rad/giây. Chậm tới mức phải nhìn vài giây mới nhận ra. */
const SPIN = 0.045;

/** Nghiêng tối đa theo con trỏ, radian (~4°). */
const TILT_MAX = 0.07;

/**
 * Quả cầu mạng lưới tình báo tài chính.
 *
 * Vẽ bằng canvas 2D nhưng toán là 3D thật: điểm nằm trên mặt cầu đơn vị, xoay
 * quanh trục Y, rồi chiếu phối cảnh. Độ sâu quyết định kích thước và độ mờ nên
 * mắt vẫn đọc ra khối cầu.
 *
 * Không dùng WebGL có chủ đích. Ba thư viện 3D cộng lại nặng hơn toàn bộ phần
 * còn lại của trang đăng nhập, mà thứ cần vẽ chỉ là vài chục điểm và vài chục
 * đoạn thẳng. Đổi lại còn một lợi ích thật: không có WebGL thì không có trường
 * hợp WebGL không khả dụng, nên màn hình này chạy ở mọi nơi form chạy được.
 */
export function LoginNetworkScene({ size, reducedMotion }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const dataRef = useRef<SceneData | null>(null);
  const pointerRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const g = canvas.getContext("2d");
    if (!g) return;

    if (!dataRef.current) dataRef.current = buildSceneData();
    const data = dataRef.current;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(size * dpr);
    canvas.height = Math.round(size * dpr);

    const cx = size / 2;
    const cy = size / 2;
    const radius = size * 0.31;
    // Khoảng cách camera tính theo bán kính: giữ phối cảnh không đổi khi đổi cỡ.
    const camera = radius * 3.6;

    let raf = 0;
    let start = performance.now();
    let last = start;
    let spin = 0;
    let tiltX = 0;
    let tiltY = 0;

    const project = (x: number, y: number, z: number) => {
      // Xoay quanh Y (tự quay), rồi nghiêng nhẹ theo con trỏ.
      const cosS = Math.cos(spin);
      const sinS = Math.sin(spin);
      let px = x * cosS + z * sinS;
      let pz = -x * sinS + z * cosS;
      let py = y;

      const cosT = Math.cos(tiltX);
      const sinT = Math.sin(tiltX);
      const ny = py * cosT - pz * sinT;
      pz = py * sinT + pz * cosT;
      py = ny;

      const cosY = Math.cos(tiltY);
      const sinY = Math.sin(tiltY);
      const nx = px * cosY + pz * sinY;
      pz = -px * sinY + pz * cosY;
      px = nx;

      const depth = camera / (camera - pz * radius);
      return {
        sx: cx + px * radius * depth,
        sy: cy + py * radius * depth,
        // 0 ở mặt sau, 1 ở mặt trước — dùng cho cả alpha lẫn cỡ điểm.
        front: (pz + 1) / 2,
      };
    };

    const draw = (now: number) => {
      const elapsed = (now - start) / 1000;
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!reducedMotion) spin += SPIN * dt;

      const target = pointerRef.current;
      tiltY += (target.x * TILT_MAX - tiltY) * 0.06;
      tiltX += (target.y * TILT_MAX - tiltX) * 0.06;

      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, size, size);

      // Quầng khí quyển — một lớp gradient duy nhất, không phải mesh.
      const halo = g.createRadialGradient(cx, cy, radius * 0.72, cx, cy, radius * 1.62);
      halo.addColorStop(0, "rgba(18,214,197,0.16)");
      halo.addColorStop(0.55, "rgba(49,133,255,0.085)");
      halo.addColorStop(1, "rgba(3,10,17,0)");
      g.fillStyle = halo;
      g.beginPath();
      g.arc(cx, cy, radius * 1.62, 0, Math.PI * 2);
      g.fill();

      // Vành đai chân đế: hai ellipse mảnh, gợi mặt phẳng tham chiếu.
      [1.34, 1.62].forEach((k, i) => {
        g.beginPath();
        g.ellipse(cx, cy + radius * 0.06, radius * k, radius * k * 0.19, 0, 0, Math.PI * 2);
        g.strokeStyle = i === 0 ? "rgba(18,214,197,0.22)" : "rgba(49,133,255,0.12)";
        g.lineWidth = 1;
        g.stroke();
      });

      // Lưới kinh tuyến và vĩ tuyến.
      //
      // Chỉ có kinh tuyến thì mắt đọc ra một nắm đường cong chứ không ra khối
      // cầu — phải có cả hai chiều thì bề mặt mới hiện hình.
      g.strokeStyle = "rgba(133,173,209,0.10)";
      g.lineWidth = 1;
      for (let m = 0; m < 8; m++) {
        const a = (m / 8) * Math.PI;
        g.beginPath();
        for (let t = 0; t <= 44; t++) {
          const v = (t / 44) * Math.PI - Math.PI / 2;
          const p = project(Math.cos(v) * Math.cos(a), Math.sin(v), Math.cos(v) * Math.sin(a));
          if (t === 0) g.moveTo(p.sx, p.sy);
          else g.lineTo(p.sx, p.sy);
        }
        g.stroke();
      }
      for (let l = 1; l < 6; l++) {
        const lat = (l / 6) * Math.PI - Math.PI / 2;
        const ring = Math.cos(lat);
        const yy = Math.sin(lat);
        g.beginPath();
        for (let t = 0; t <= 48; t++) {
          const a = (t / 48) * Math.PI * 2;
          const p = project(Math.cos(a) * ring, yy, Math.sin(a) * ring);
          if (t === 0) g.moveTo(p.sx, p.sy);
          else g.lineTo(p.sx, p.sy);
        }
        g.stroke();
      }

      const projected = data.points.map((p) => project(p.x, p.y, p.z));

      // Cạnh mạng lưới. Mặt sau mờ hẳn để khối cầu có chiều sâu.
      data.links.forEach((link) => {
        const a = projected[link.a];
        const b = projected[link.b];
        const front = (a.front + b.front) / 2;
        g.beginPath();
        g.moveTo(a.sx, a.sy);
        g.lineTo(b.sx, b.sy);
        g.strokeStyle = `rgba(18,214,197,${(0.09 + front * 0.38) * link.weight})`;
        g.lineWidth = 0.6 + front * 0.5;
        g.stroke();
      });

      // Cung giao dịch vồng khỏi mặt cầu, kèm một chấm chạy dọc.
      data.arcs.forEach((arc) => {
        const pa = data.points[arc.a];
        const pb = data.points[arc.b];
        const steps = 28;
        let headX = 0;
        let headY = 0;
        let headFront = 0;
        const progress = reducedMotion ? 0.5 : (elapsed * 0.18 + arc.offset) % 1;

        g.beginPath();
        for (let s = 0; s <= steps; s++) {
          const t = s / steps;
          // Nội suy tuyến tính rồi chuẩn hoá về mặt cầu = cung tròn lớn.
          const mx = pa.x + (pb.x - pa.x) * t;
          const my = pa.y + (pb.y - pa.y) * t;
          const mz = pa.z + (pb.z - pa.z) * t;
          const len = Math.hypot(mx, my, mz) || 1;
          const lift = 1 + Math.sin(t * Math.PI) * arc.lift;
          const p = project((mx / len) * lift, (my / len) * lift, (mz / len) * lift);
          if (s === 0) g.moveTo(p.sx, p.sy);
          else g.lineTo(p.sx, p.sy);
          if (Math.abs(t - progress) < 1 / steps) {
            headX = p.sx;
            headY = p.sy;
            headFront = p.front;
          }
        }
        g.strokeStyle = "rgba(95,232,219,0.42)";
        g.lineWidth = 1.1;
        g.stroke();

        if (headX && headFront > 0.25) {
          g.beginPath();
          g.arc(headX, headY, 2.2, 0, Math.PI * 2);
          g.fillStyle = `rgba(159,247,238,${0.5 + headFront * 0.5})`;
          g.fill();
        }
      });

      // Đỉnh. Vẽ từ sau ra trước để đỉnh gần che đỉnh xa.
      const order = data.points
        .map((p, i) => ({ p, i, front: projected[i].front }))
        .sort((x, y) => x.front - y.front);

      order.forEach(({ p, i, front }) => {
        const q = projected[i];
        const pulse = reducedMotion ? 0.5 : (Math.sin(elapsed * (p.alert ? 1.5 : 2.4) + p.phase) + 1) / 2;
        const r = (1.1 + p.size * 1.5) * (0.55 + front * 0.75);

        if (p.alert) {
          const glow = 0.18 + pulse * 0.3;
          g.beginPath();
          g.arc(q.sx, q.sy, r * (2.6 + pulse * 1.1), 0, Math.PI * 2);
          g.fillStyle = `rgba(255,77,97,${glow * front})`;
          g.fill();
        }

        g.beginPath();
        g.arc(q.sx, q.sy, r, 0, Math.PI * 2);
        g.fillStyle = p.alert
          ? `rgba(255,107,124,${0.55 + front * 0.45})`
          : `rgba(${95 + pulse * 40},${232},${219},${0.2 + front * 0.7})`;
        g.fill();
      });

      raf = requestAnimationFrame(draw);
    };

    // Người dùng tắt hiệu ứng thì vẽ đúng một khung rồi thôi — không giữ vòng
    // lặp chạy nền chỉ để không làm gì.
    if (reducedMotion) {
      draw(performance.now());
      cancelAnimationFrame(raf);
      raf = 0;
    } else {
      raf = requestAnimationFrame(draw);
    }

    // Tab bị ẩn thì trình duyệt đã dừng rAF, nhưng mốc thời gian vẫn trôi —
    // không đặt lại thì lúc quay về quả cầu nhảy một đoạn.
    const onVisibility = () => {
      if (document.hidden) {
        if (raf) cancelAnimationFrame(raf);
        raf = 0;
      } else if (!reducedMotion && !raf) {
        const now = performance.now();
        start = now - 0;
        last = now;
        raf = requestAnimationFrame(draw);
      }
    };

    const onPointer = (e: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      pointerRef.current = {
        x: ((e.clientX - rect.left) / rect.width - 0.5) * 2,
        y: ((e.clientY - rect.top) / rect.height - 0.5) * 2,
      };
    };

    document.addEventListener("visibilitychange", onVisibility);
    if (!reducedMotion) window.addEventListener("pointermove", onPointer, { passive: true });

    return () => {
      if (raf) cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onPointer);
    };
  }, [size, reducedMotion]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      // Canvas nằm dưới mọi thứ và không nhận chuột: nó tuyệt đối không được
      // chắn được click vào form hay chặn bôi đen chữ.
      className="pointer-events-none select-none"
      style={{ width: size, height: size, color: C.primary }}
    />
  );
}
