/**
 * Hệ chuyển động của console.
 *
 * Nguyên tắc: mọi animation phải trả lời được câu "vì sao thứ này chuyển động?".
 * Chỉ có bảy câu trả lời được chấp nhận — giữ liên tục không gian, báo đổi trạng
 * thái, thể hiện phân cấp, xác nhận thao tác của người dùng, dẫn sự chú ý, mô tả
 * dòng chảy dữ liệu, và báo hệ thống đang sống. Không có "trông cho ngầu".
 *
 * Năm lớp chuyển động:
 *
 *   L0 Ambient    — nhịp nền, chỉ báo đang sống (vô hạn nhưng gần như không thấy)
 *   L1 Feedback   — hover, press, focus, toggle          (~80–140ms)
 *   L2 State      — dropdown, tab, badge, tooltip        (~140–260ms)
 *   L3 Layout     — sidebar, drawer, panel, bảng         (~220–360ms)
 *   L4 Spatial    — chuyển 2D↔3D, camera bản đồ          (~400–700ms)
 */

import { useReducedMotion, type Transition, type Variants } from "motion/react";

import { duration, easing } from "./tokens";

export const motionTokens = { duration, easing } as const;

const std = easing.standard as unknown as [number, number, number, number];
const enterEase = easing.enter as unknown as [number, number, number, number];
const exitEase = easing.exit as unknown as [number, number, number, number];

/** Transition dựng sẵn cho từng lớp — không rải số 0.27 / 0.34 khắp repo. */
export const transitions = {
  feedback: { duration: duration.fast, ease: std } satisfies Transition,
  state: { duration: duration.normal, ease: std } satisfies Transition,
  enter: { duration: duration.normal, ease: enterEase } satisfies Transition,
  exit: { duration: duration.fast, ease: exitEase } satisfies Transition,
  layout: { duration: duration.slow, ease: std } satisfies Transition,
  spatial: { duration: duration.spatial, ease: std } satisfies Transition,
} as const;

/**
 * Chuyển màn hình. Chỉ mờ dần và trôi 4px — console không phải ứng dụng
 * trình chiếu, và trôi 50px làm người đọc mất chỗ đang nhìn.
 */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 4 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.18, ease: enterEase } },
  exit: { opacity: 0, y: -2, transition: { duration: 0.12, ease: exitEase } },
};

/**
 * Vào theo nhóm. Độ trễ giữa các phần tử cố ý rất nhỏ: đây là tín hiệu về thứ
 * tự đọc, không phải màn trình diễn. Một lưới sáu KPI sẽ vào xong trong 0.2s.
 */
export const staggerContainer: Variants = {
  initial: {},
  animate: { transition: { staggerChildren: 0.035, delayChildren: 0.02 } },
};

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0, transition: transitions.enter },
};

/** Popover, dropdown, tooltip: mờ + nảy nhẹ về phía điểm neo. */
export const popVariants: Variants = {
  initial: { opacity: 0, scale: 0.97, y: -2 },
  animate: { opacity: 1, scale: 1, y: 0, transition: transitions.state },
  exit: { opacity: 0, scale: 0.98, y: -2, transition: transitions.exit },
};

/** Inspector và drawer trượt vào từ mép phải. */
export const inspectorVariants: Variants = {
  initial: { opacity: 0, x: 12 },
  animate: { opacity: 1, x: 0, transition: transitions.layout },
  exit: { opacity: 0, x: 12, transition: transitions.exit },
};

/** Hàng bảng và mục danh sách: vào/ra nhẹ, có layout reposition. */
export const rowVariants: Variants = {
  initial: { opacity: 0, y: -4 },
  animate: { opacity: 1, y: 0, transition: transitions.state },
  exit: { opacity: 0, transition: transitions.exit },
};

/**
 * Bọc `prefers-reduced-motion` của Motion.
 *
 * `useReducedMotion()` trả `null` khi chưa biết; ở đây quy về boolean để chỗ
 * dùng không phải xử lý ba trạng thái. Mọi animation mới PHẢI đi qua hook này
 * hoặc qua `safeTransition` bên dưới.
 */
export function useReduced(): boolean {
  return useReducedMotion() === true;
}

/**
 * Rút một transition về gần như tức thời khi người dùng yêu cầu giảm chuyển
 * động. Không trả về `duration: 0` — Motion vẫn cần một khung để chạy callback
 * `onAnimationComplete`, mà nhiều orchestrator ở đây bám vào đó.
 */
export function safeTransition(base: Transition, reduced: boolean): Transition {
  return reduced ? { duration: 0.01 } : base;
}

/** Biến thể tương ứng, dùng cho các component nhận `variants`. */
export function safeVariants(base: Variants, reduced: boolean): Variants {
  if (!reduced) return base;
  return {
    initial: { opacity: 0 },
    animate: { opacity: 1, transition: { duration: 0.01 } },
    exit: { opacity: 0, transition: { duration: 0.01 } },
  };
}
