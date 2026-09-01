/**
 * Chuyển dữ liệu AML sang mô tả hình học cho quả cầu.
 *
 * File này KHÔNG import Cesium. Nó chỉ quyết định "vẽ cái gì, màu gì, dày bao
 * nhiêu" dựa trên nghiệp vụ; còn "vẽ bằng API nào" là việc của cesium/layers.ts.
 * Nhờ vậy toàn bộ luật rủi ro và luật lọc kiểm thử được mà không cần WebGL.
 */

import type { MapData, MapFlow, MapHub } from "../../../components/fc/WorldMap";
import { channelColor, routeColor } from "../../../design/adapters/mapTheme";
import { severityOf as riskSeverityOf } from "../../../design/risk";

/**
 * Bảng màu kênh và bảng màu mức độ đều lấy từ design token, không chép lại
 * hằng số ở đây: bản đồ, chú giải dưới bản đồ và bảng xếp hạng bên phải phải
 * cùng một màu cho cùng một kênh, mà ba chỗ đó nằm ở ba file khác nhau.
 */
export const CHANNEL_COLOR: Record<string, string> = channelColor;

/**
 * Mức "bình thường" dùng xanh dương chứ không dùng teal: trên bản đồ, teal
 * dành riêng cho thực thể đang được chọn (§4). Hành lang bình thường vốn đã mờ
 * và nét đứt nên không cần thêm màu để nói rằng nó không đáng chú ý.
 */
export const RISK_COLOR = routeColor;

export type Severity = "ok" | "warn" | "crit";

export interface NodeDescriptor {
  id: string;
  name: string;
  lon: number;
  lat: number;
  severity: Severity;
  color: string;
  /** Đường kính chấm tính bằng pixel. */
  pixelSize: number;
  /** Nhãn chỉ hiện thường trực với node quan trọng — xem §12. */
  labelAlways: boolean;
  hub: MapHub;
}

export interface RouteDescriptor {
  id: string;
  from: { lon: number; lat: number };
  to: { lon: number; lat: number };
  severity: Severity;
  color: string;
  width: number;
  /** Nét đứt cho luồng bình thường; liền cho đáng ngờ và nghiêm trọng. */
  dashed: boolean;
  /** Chỉ luồng đáng ngờ/nghiêm trọng mới chạy hiệu ứng dòng chảy. */
  animated: boolean;
  alpha: number;
  /** Độ cao đỉnh cung so với mặt đất, tính bằng mét. */
  apexMeters: number;
  flow: MapFlow;
}

export interface GlobeScene {
  nodes: NodeDescriptor[];
  routes: RouteDescriptor[];
  /** Bản ghi bị loại vì toạ độ hỏng — để lộ ra chứ không nuốt im lặng (§26). */
  rejected: { kind: "node" | "route"; id: string; reason: string }[];
}

export interface FilterState {
  layers: Record<string, boolean>;
  severity: string;
  typology: string;
  topN: number;
  suspiciousOnly: boolean;
}

/**
 * Ngưỡng rủi ro. Uỷ quyền cho `design/risk` để bản đồ, bảng cảnh báo và đồ thị
 * không thể trôi khỏi nhau — trước đây ngưỡng này được chép lại ở ba nơi.
 */
export function severityOf(risk: number): Severity {
  return riskSeverityOf(risk);
}

/**
 * Toạ độ hợp lệ theo WGS84.
 *
 * Một vĩ độ NaN hay kinh độ 999 lọt xuống Cesium sẽ thành đường kẻ vắt ngang
 * quả cầu hoặc thực thể ở tâm Trái Đất — nhìn như lỗi dựng hình chứ không ai
 * đoán được là dữ liệu bẩn.
 */
export function isValidCoordinate(lon: unknown, lat: unknown): boolean {
  return (
    typeof lon === "number" &&
    typeof lat === "number" &&
    Number.isFinite(lon) &&
    Number.isFinite(lat) &&
    lon >= -180 &&
    lon <= 180 &&
    lat >= -90 &&
    lat <= 90
  );
}

/**
 * Khoảng cách vòng lớn, đơn vị mét. Dùng để chọn độ cao đỉnh cung: hành lang
 * càng dài thì cung càng phải nhấc cao mới đọc được trên nền cầu.
 */
export function greatCircleMeters(
  aLon: number,
  aLat: number,
  bLon: number,
  bLat: number,
): number {
  const R = 6_371_000;
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLon = toRad(bLon - aLon);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(aLat)) * Math.cos(toRad(bLat)) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function nodeSeverity(hub: MapHub): Severity {
  return severityOf(hub.riskN ?? 0);
}

/** Lọc luồng theo đúng thứ tự mà engine canvas cũ áp dụng, để hai chế độ khớp nhau. */
function applyFilters(flows: MapFlow[], filter: FilterState): MapFlow[] {
  const ranked = [...flows].sort((a, b) => (b.riskN ?? 0) - (a.riskN ?? 0));
  const topIds = filter.topN > 0 ? new Set(ranked.slice(0, filter.topN).map((f) => f.id)) : null;

  return flows.filter((f) => {
    if (filter.layers && filter.layers[f.ch] === false) return false;
    if (filter.severity === "warn" && f.risk === "ok") return false;
    if (filter.severity === "crit" && f.risk !== "crit") return false;
    if (filter.typology !== "all" && f.typ !== filter.typology) return false;
    if (filter.suspiciousOnly && f.risk === "ok") return false;
    if (topIds && !topIds.has(f.id)) return false;
    return true;
  });
}

export function buildScene(data: MapData | null, filter: FilterState): GlobeScene {
  const rejected: GlobeScene["rejected"] = [];
  if (!data) return { nodes: [], routes: [], rejected };

  const nodes: NodeDescriptor[] = [];
  for (const hub of data.hubs) {
    if (!isValidCoordinate(hub.lon, hub.lat)) {
      rejected.push({ kind: "node", id: hub.id, reason: `toạ độ không hợp lệ (${hub.lon}, ${hub.lat})` });
      continue;
    }
    const severity = nodeSeverity(hub);
    nodes.push({
      id: hub.id,
      name: hub.name,
      lon: hub.lon,
      lat: hub.lat,
      severity,
      color: RISK_COLOR[severity],
      // Chuẩn hoá theo `size` (đã là thang log của khối lượng ở WorldPage) chứ
      // không theo giá trị giao dịch thô — nếu không, một trung tâm sẽ nuốt cả
      // châu lục còn các trung tâm khác thành chấm không thấy.
      pixelSize: severity === "crit" ? 13 : severity === "warn" ? 11 : 9,
      labelAlways: severity === "crit",
      hub,
    });
  }

  const routes: RouteDescriptor[] = [];
  for (const flow of applyFilters(data.flows, filter)) {
    if (!isValidCoordinate(flow.slon, flow.slat) || !isValidCoordinate(flow.tlon, flow.tlat)) {
      rejected.push({
        kind: "route",
        id: flow.id,
        reason: `toạ độ không hợp lệ (${flow.slon},${flow.slat} → ${flow.tlon},${flow.tlat})`,
      });
      continue;
    }
    const severity = (flow.risk as Severity) ?? "ok";
    const crit = severity === "crit";
    const warn = severity === "warn";
    const span = greatCircleMeters(flow.slon, flow.slat, flow.tlon, flow.tlat);
    routes.push({
      id: flow.id,
      from: { lon: flow.slon, lat: flow.slat },
      to: { lon: flow.tlon, lat: flow.tlat },
      severity,
      // Nghiêm trọng dùng màu rủi ro; còn lại giữ màu kênh để đọc được loại dòng tiền.
      color: crit ? RISK_COLOR.crit : (CHANNEL_COLOR[flow.ch] ?? CHANNEL_COLOR.bank),
      width: crit ? 3.4 : warn ? 2.4 : 1.4,
      dashed: !crit && !warn,
      animated: crit || warn,
      alpha: crit ? 0.95 : warn ? 0.8 : 0.42,
      // Nhấc cung vừa đủ tách khỏi bề mặt. 12% chiều dài từng thử và trông như
      // quỹ đạo vệ tinh chứ không phải dòng tiền; 5% có trần giữ cung bám sát
      // Trái Đất kể cả với hành lang xuyên Đại Tây Dương.
      apexMeters: Math.min(420_000, Math.max(90_000, span * 0.05)),
      flow,
    });
  }

  return { nodes, routes, rejected };
}
