/**
 * Đồng bộ mô tả hình học AML vào Cesium.
 *
 * Chỉ file này biết tới API Cesium. Luật nghiệp vụ nằm ở adapters/toCesium.ts.
 */

import {
  Cartesian3,
  Cartographic,
  Color,
  EllipsoidGeodesic,
  Entity,
  HorizontalOrigin,
  LabelStyle,
  ConstantProperty,
  DistanceDisplayCondition,
  JulianDate,
  NearFarScalar,
  PolylineDashMaterialProperty,
  PolylineGlowMaterialProperty,
  VerticalOrigin,
  Viewer,
} from "cesium";

import type { GlobeScene, NodeDescriptor, RouteDescriptor } from "../adapters/toCesium";

/** Số điểm lấy mẫu trên mỗi cung. Đủ mượt ở mức toàn cầu, không phí đỉnh. */
const ARC_SAMPLES = 64;

/**
 * Dựng các điểm của một cung trắc địa, nhấc dần lên tới đỉnh ở giữa.
 *
 * Dùng EllipsoidGeodesic thay vì nội suy tuyến tính kinh/vĩ độ: nội suy tuyến
 * tính vẽ sai đường ở vĩ độ cao và tạo ra một vệt vòng quanh Trái Đất khi hành
 * lang cắt qua kinh tuyến 180° (§27).
 */
export function arcPositions(route: RouteDescriptor): Cartesian3[] {
  const start = Cartographic.fromDegrees(route.from.lon, route.from.lat);
  const end = Cartographic.fromDegrees(route.to.lon, route.to.lat);
  const geodesic = new EllipsoidGeodesic(start, end);
  const points: Cartesian3[] = [];
  for (let i = 0; i <= ARC_SAMPLES; i++) {
    const t = i / ARC_SAMPLES;
    const point = geodesic.interpolateUsingFraction(t, new Cartographic());
    // Profile hình sin: bằng 0 ở hai đầu nên cung chạm đất đúng tại hai trung tâm.
    const height = Math.sin(t * Math.PI) * route.apexMeters;
    points.push(Cartesian3.fromRadians(point.longitude, point.latitude, height));
  }
  return points;
}

function css(color: string, alpha = 1): Color {
  return Color.fromCssColorString(color).withAlpha(alpha);
}

function addNode(viewer: Viewer, node: NodeDescriptor): Entity {
  return viewer.entities.add({
    id: `node:${node.id}`,
    position: Cartesian3.fromDegrees(node.lon, node.lat),
    point: {
      pixelSize: node.pixelSize,
      color: css(node.color, 0.95),
      outlineColor: css(node.color, 0.35),
      outlineWidth: node.severity === "ok" ? 3 : 5,
      // Chấm phải bị Trái Đất che khi nằm ở nửa bên kia (§28).
      disableDepthTestDistance: 0,
    },
    label: {
      text: node.name,
      font: "500 12px Geist, system-ui, sans-serif",
      fillColor: css("#E6EDF3", 0.92),
      outlineColor: css("#080D12", 0.9),
      outlineWidth: 3,
      style: LabelStyle.FILL_AND_OUTLINE,
      horizontalOrigin: HorizontalOrigin.LEFT,
      verticalOrigin: VerticalOrigin.BOTTOM,
      pixelOffset: new Cartesian3(10, -6, 0),
      // Ở mức toàn cầu chỉ nhãn của node nghiêm trọng hiện thường trực; còn lại
      // chỉ hiện khi camera đã xuống gần, tránh chữ đè kín Trái Đất (§12).
      distanceDisplayCondition: node.labelAlways
        ? undefined
        : new DistanceDisplayCondition(0, 12_000_000),
      translucencyByDistance: new NearFarScalar(6_000_000, 1.0, 26_000_000, 0.0),
    },
    properties: { kind: "node", payload: node.hub, baseOutline: node.severity === "ok" ? 3 : 5 },
  });
}

function addRoute(viewer: Viewer, route: RouteDescriptor): Entity {
  const base = css(route.color, route.alpha);
  const material = route.dashed
    ? new PolylineDashMaterialProperty({ color: base, dashLength: 14 })
    : route.severity === "crit"
      ? new PolylineGlowMaterialProperty({ color: base, glowPower: 0.22, taperPower: 0.9 })
      : base;

  return viewer.entities.add({
    id: `route:${route.id}`,
    polyline: {
      positions: arcPositions(route),
      width: route.width,
      material,
      // `arcType` để mặc định NONE vì các điểm đã là toạ độ 3D tuyệt đối; không
      // đặt depthFailMaterial để cung phía bên kia Trái Đất bị che tự nhiên.
      clampToGround: false,
    },
    properties: { kind: "route", payload: route.flow, baseWidth: route.width },
  });
}

/**
 * Vẽ lại toàn bộ lớp AML.
 *
 * Xoá rồi thêm lại thay vì cập nhật từng thực thể: ở quy mô Top 50 thì chi phí
 * không đáng kể, mà tránh được cả một lớp lỗi đồng bộ trạng thái. Camera và chế
 * độ cảnh không bị đụng tới, nên lọc không làm nhảy khung nhìn (§16).
 */
export function syncScene(viewer: Viewer, scene: GlobeScene): void {
  viewer.entities.suspendEvents();
  try {
    viewer.entities.removeAll();
    for (const node of scene.nodes) addNode(viewer, node);
    for (const route of scene.routes) addRoute(viewer, route);
  } finally {
    viewer.entities.resumeEvents();
  }

  for (const bad of scene.rejected) {
    console.warn(`[globe] bỏ qua ${bad.kind} ${bad.id}: ${bad.reason}`);
  }
}

/**
 * Làm nổi thực thể đang chọn mà không dựng lại cả cảnh.
 *
 * Bề rộng gốc được cất trong `properties` lúc tạo, nên bỏ chọn là trả về đúng
 * giá trị cũ chứ không phải một hằng số đoán mò.
 */
export function highlight(viewer: Viewer, flowId: string | null, hubId: string | null): void {
  for (const entity of viewer.entities.values) {
    const base = entity.properties?.getValue(JulianDate.now()) as
      | { baseWidth?: number; baseOutline?: number }
      | undefined;

    if (entity.polyline && base?.baseWidth !== undefined) {
      entity.polyline.width = new ConstantProperty(
        entity.id === `route:${flowId}` ? base.baseWidth + 2.2 : base.baseWidth,
      );
    }
    if (entity.point && base?.baseOutline !== undefined) {
      entity.point.outlineWidth = new ConstantProperty(
        entity.id === `node:${hubId}` ? base.baseOutline + 4 : base.baseOutline,
      );
    }
  }
}
