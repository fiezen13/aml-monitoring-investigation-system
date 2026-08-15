/**
 * Hành lang giao dịch → mô tả chuyển động.
 *
 * File này KHÔNG import MapLibre lẫn Cesium, và cũng không biết gì về WebGL. Nó
 * chỉ trả lời một câu hỏi: "hành lang này phải chảy nhanh bao nhiêu, dày bao
 * nhiêu, sáng bao nhiêu, màu gì". Cả hai bộ dựng hình đọc cùng kết quả ấy — đó
 * là lý do vệt sáng trên bản đồ phẳng và vệt sáng trên quả cầu luôn ở cùng một
 * chỗ trên cùng một hành lang.
 */

import { flowMotion, flowScale, type FlowAnimationSpec } from "../../../design/flow";
import type { RouteDescriptor } from "./toCesium";

/**
 * Lệch pha tất định theo id hành lang.
 *
 * Nếu mọi hành lang cùng khởi hành ở 0 thì cả bản đồ nhấp nháy đồng loạt như
 * một hàng đèn nháy — nhìn ra ngay là hiệu ứng, không phải dữ liệu. Băm id cho
 * mỗi hành lang một pha riêng nhưng ổn định giữa các lần dựng lại và giữa hai
 * bộ dựng hình; `Math.random()` sẽ hỏng cả hai tính chất đó.
 *
 * FNV-1a 32 bit: đủ tản đều cho mục đích này và viết gọn trong sáu dòng.
 */
export function routePhase(id: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    hash ^= id.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return ((hash >>> 0) % 10_000) / 10_000;
}

/** Chuẩn hoá theo thang log rồi kẹp về 0–1. */
function normalizeLog(value: number, min: number, max: number): number {
  if (!Number.isFinite(value) || value <= 0) return 0;
  const t = (Math.log10(value) - Math.log10(min)) / (Math.log10(max) - Math.log10(min));
  return Math.min(1, Math.max(0, t));
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export interface FlowSelection {
  selectedFlowId: string | null;
  hoveredFlowId?: string | null;
  /**
   * Người dùng yêu cầu giảm chuyển động.
   *
   * Xử lý ở tầng này chứ không ở từng bộ dựng hình: nếu mỗi renderer tự quyết
   * thì sẽ có hai định nghĩa "giảm chuyển động", và sớm muộn chúng lệch nhau.
   * Ở đây nó chỉ là một mô tả chuyển động khác — vệt đứng yên, phần sáng của vệt
   * dồn vào đường nền để không mất thông tin nào.
   */
  reducedMotion?: boolean;
}

/**
 * Dựng mô tả chuyển động cho một hành lang.
 *
 * Ba biến, ba nghĩa:
 *
 *   bề rộng → khối lượng (thang log; chênh lệch giữa các hành lang là vài bậc
 *             độ lớn, thang tuyến tính sẽ chỉ thấy đúng một đường dày)
 *   tốc độ  → số giao dịch trong cửa sổ, tức mật độ hoạt động
 *   màu     → mức rủi ro, lấy nguyên từ `RouteDescriptor.color` (đã qua
 *             `design/risk` và `design/adapters/mapTheme`)
 *
 * Khối lượng không có trong dữ liệu thì bề rộng lùi về mức tối thiểu chứ không
 * bịa ra một giá trị trông hợp lý.
 */
export function buildFlowSpec(route: RouteDescriptor, selection: FlowSelection): FlowAnimationSpec {
  const selected = selection.selectedFlowId === route.id;
  const hovered = selection.hoveredFlowId === route.id;
  const dimmed = selection.selectedFlowId != null && !selected;

  const volumeT = normalizeLog(route.flow.volUsd ?? 0, flowScale.volumeMinUsd, flowScale.volumeMaxUsd);
  const activityT = normalizeLog(route.flow.txn ?? 0, flowScale.txnMin, flowScale.txnMax);

  const baseOpacity =
    route.severity === "crit"
      ? flowMotion.baseOpacityCritical
      : route.severity === "warn"
        ? flowMotion.baseOpacitySuspicious
        : flowMotion.baseOpacity;

  let width = lerp(flowMotion.minWidth, flowMotion.maxWidth, volumeT);
  if (selected) width += flowMotion.selectedWidthBonus;
  else if (hovered) width += flowMotion.hoverWidthBonus;

  const trailOpacity = selected
    ? flowMotion.selectedTrailOpacity
    : dimmed
      ? flowMotion.trailOpacity * 0.35
      : flowMotion.trailOpacity;
  const resolvedBase = dimmed ? flowMotion.inactiveOpacity : baseOpacity;

  if (selection.reducedMotion) {
    return {
      id: route.id,
      // Tốc độ 0 là tín hiệu cho cả hai bộ dựng hình: không có gì phải chạy, và
      // ở phía Cesium nó còn cho phép đánh dấu vật liệu là hằng số.
      speed: 0,
      phase: routePhase(route.id),
      trailLength: selected ? flowMotion.selectedTrailLength : flowMotion.normalTrailLength,
      baseOpacity: Math.min(0.9, resolvedBase + trailOpacity * 0.45),
      trailOpacity: 0,
      width,
      color: route.color,
      selected,
      dimmed,
      dashed: route.dashed,
    };
  }

  return {
    id: route.id,
    speed: lerp(flowMotion.minSpeed, flowMotion.maxSpeed, activityT),
    phase: routePhase(route.id),
    trailLength: selected ? flowMotion.selectedTrailLength : flowMotion.normalTrailLength,
    baseOpacity: resolvedBase,
    trailOpacity,
    width,
    color: route.color,
    selected,
    dimmed,
    // Nét đứt giữ đúng chú giải hiện có: "nét đứt = bình thường".
    dashed: route.dashed,
  };
}

export function buildFlowSpecs(
  routes: RouteDescriptor[],
  selection: FlowSelection,
): Map<string, FlowAnimationSpec> {
  const specs = new Map<string, FlowAnimationSpec>();
  for (const route of routes) specs.set(route.id, buildFlowSpec(route, selection));
  return specs;
}
