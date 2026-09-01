/**
 * Hình học hành lang giao dịch cho bản đồ phẳng 2D.
 *
 * Tách hẳn khỏi cung 3D: cung của quả cầu có độ cao và toạ độ Cartesian tuyệt
 * đối, đem sang Mercator sẽ ra những đường thòng xuống Nam Cực hoặc chạy khỏi
 * khung. Ở đây chỉ có kinh độ và vĩ độ, không có độ cao.
 */

/** Số điểm lấy mẫu trên mỗi vòng lớn. Đủ mượt ở mức thế giới, không phí đỉnh. */
const SAMPLES = 48;

/** Dưới ngưỡng này thì vẽ thẳng — cong một đoạn 300 km chỉ tạo nhiễu. */
const MIN_CURVE_DEGREES = 3;

export type Position = [number, number];

const toRad = (d: number) => (d * Math.PI) / 180;
const toDeg = (r: number) => (r * 180) / Math.PI;

/**
 * Nội suy vòng lớn giữa hai điểm (slerp trên mặt cầu).
 *
 * Không nội suy tuyến tính kinh/vĩ độ: đường sẽ lệch nhiều ở vĩ độ cao, và một
 * hành lang Tokyo → Los Angeles sẽ vẽ vòng ngược qua châu Âu.
 */
export function greatCirclePoints(a: Position, b: Position, samples = SAMPLES): Position[] {
  const [lon1, lat1] = [toRad(a[0]), toRad(a[1])];
  const [lon2, lat2] = [toRad(b[0]), toRad(b[1])];

  const d =
    2 *
    Math.asin(
      Math.min(
        1,
        Math.sqrt(
          Math.sin((lat2 - lat1) / 2) ** 2 +
            Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2,
        ),
      ),
    );

  // Hai điểm trùng nhau: trả về chính nó, tránh chia cho sin(0).
  if (d < 1e-9) return [a, b];

  const points: Position[] = [];
  for (let i = 0; i <= samples; i++) {
    const f = i / samples;
    const A = Math.sin((1 - f) * d) / Math.sin(d);
    const B = Math.sin(f * d) / Math.sin(d);
    const x = A * Math.cos(lat1) * Math.cos(lon1) + B * Math.cos(lat2) * Math.cos(lon2);
    const y = A * Math.cos(lat1) * Math.sin(lon1) + B * Math.cos(lat2) * Math.sin(lon2);
    const z = A * Math.sin(lat1) + B * Math.sin(lat2);
    points.push([toDeg(Math.atan2(y, x)), toDeg(Math.atan2(z, Math.sqrt(x * x + y * y)))]);
  }
  return points;
}

/**
 * Cắt đường tại kinh tuyến ±180°.
 *
 * MapLibre nối hai điểm liên tiếp theo đúng số kinh độ nhận được. Một bước nhảy
 * từ +179 sang −179 sẽ được vẽ thành đường dài 358° chạy ngược hết bản đồ —
 * đúng triệu chứng "route vòng sai qua thế giới" với hành lang Nhật → Mỹ.
 *
 * Trả về nhiều đoạn; nơi cắt được chèn điểm tại đúng ±180 để đường chạm mép
 * bản đồ thay vì đứt lơ lửng.
 */
export function splitAntimeridian(points: Position[]): Position[][] {
  if (points.length < 2) return points.length ? [points] : [];

  const segments: Position[][] = [];
  let current: Position[] = [points[0]];

  for (let i = 1; i < points.length; i++) {
    const [prevLon, prevLat] = points[i - 1];
    const [lon, lat] = points[i];
    const delta = lon - prevLon;

    if (Math.abs(delta) > 180) {
      // Đi về hướng nào thì chạm mép nào: sang đông thì cắt ở +180.
      const eastward = delta < 0;
      const edge = eastward ? 180 : -180;
      // Nội suy vĩ độ tại điểm cắt theo phần đường đã đi tới mép.
      const shifted = eastward ? lon + 360 : lon - 360;
      const t = (edge - prevLon) / (shifted - prevLon);
      const crossLat = prevLat + t * (lat - prevLat);

      current.push([edge, crossLat]);
      segments.push(current);
      current = [[-edge, crossLat], [lon, lat]];
      continue;
    }
    current.push([lon, lat]);
  }

  segments.push(current);
  return segments.filter((segment) => segment.length >= 2);
}

/**
 * Hình học 2D hoàn chỉnh của một hành lang: vòng lớn, đã cắt kinh tuyến 180°.
 *
 * Trả về mảng đoạn để dựng LineString (một đoạn) hoặc MultiLineString (nhiều).
 */
export function build2DRouteGeometry(source: Position, target: Position): Position[][] {
  const spanLon = Math.abs(target[0] - source[0]);
  const spanLat = Math.abs(target[1] - source[1]);
  const straight = Math.max(spanLon, spanLat) < MIN_CURVE_DEGREES;
  const points = straight ? [source, target] : greatCirclePoints(source, target);
  return splitAntimeridian(points);
}
