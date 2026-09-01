import { describe, expect, it } from "vitest";

import {
  build2DRouteGeometry,
  greatCirclePoints,
  splitAntimeridian,
  type Position,
} from "./routeGeometry";

const TOKYO: Position = [139.69, 35.69];
const LOS_ANGELES: Position = [-118.24, 34.05];
const NEW_YORK: Position = [-74.0, 40.71];
const LONDON: Position = [-0.13, 51.51];
const PARIS: Position = [2.35, 48.86];
const BRUSSELS: Position = [4.35, 50.85];
const BEIJING: Position = [116.4, 39.9];

/** Kinh độ lớn nhất giữa hai điểm liên tiếp — thước đo "có nhảy sai hay không". */
function maxStep(points: Position[]): number {
  let worst = 0;
  for (let i = 1; i < points.length; i++) {
    worst = Math.max(worst, Math.abs(points[i][0] - points[i - 1][0]));
  }
  return worst;
}

describe("vòng lớn", () => {
  it("bắt đầu và kết thúc đúng hai đầu", () => {
    const points = greatCirclePoints(NEW_YORK, LONDON);
    expect(points[0][0]).toBeCloseTo(NEW_YORK[0], 4);
    expect(points[points.length - 1][1]).toBeCloseTo(LONDON[1], 4);
  });

  it("New York → London cong lên phía bắc chứ không đi thẳng", () => {
    const points = greatCirclePoints(NEW_YORK, LONDON);
    const mid = points[Math.floor(points.length / 2)];
    const straightMidLat = (NEW_YORK[1] + LONDON[1]) / 2;
    // Đường bay thật qua Bắc Đại Tây Dương nằm cao hơn trung điểm tuyến tính.
    expect(mid[1]).toBeGreaterThan(straightMidLat);
  });

  it("hai điểm trùng nhau không sinh NaN", () => {
    const points = greatCirclePoints(PARIS, PARIS);
    expect(points.every(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))).toBe(true);
  });

  it("mọi toạ độ sinh ra đều nằm trong dải hợp lệ", () => {
    for (const [a, b] of [
      [TOKYO, LOS_ANGELES],
      [BEIJING, NEW_YORK],
      [LONDON, TOKYO],
    ] as const) {
      for (const [lon, lat] of greatCirclePoints(a, b)) {
        expect(lon).toBeGreaterThanOrEqual(-180.0001);
        expect(lon).toBeLessThanOrEqual(180.0001);
        expect(lat).toBeGreaterThanOrEqual(-90);
        expect(lat).toBeLessThanOrEqual(90);
      }
    }
  });
});

describe("cắt kinh tuyến 180°", () => {
  it("Tokyo → Los Angeles tách thành hai đoạn, không vòng ngược bản đồ", () => {
    const segments = build2DRouteGeometry(TOKYO, LOS_ANGELES);
    expect(segments.length).toBe(2);
    // Đây là lỗi cần chặn: một bước nhảy 358° sẽ được MapLibre vẽ thành đường
    // chạy ngược hết chiều rộng bản đồ.
    for (const segment of segments) expect(maxStep(segment)).toBeLessThan(180);
  });

  it("đoạn cắt chạm đúng mép ±180 để đường không đứt lơ lửng", () => {
    const [first, second] = build2DRouteGeometry(TOKYO, LOS_ANGELES);
    expect(Math.abs(first[first.length - 1][0])).toBeCloseTo(180, 6);
    expect(Math.abs(second[0][0])).toBeCloseTo(180, 6);
    // Vĩ độ tại điểm cắt phải liên tục giữa hai đoạn.
    expect(second[0][1]).toBeCloseTo(first[first.length - 1][1], 6);
  });

  it("hành lang không qua kinh tuyến 180° chỉ có một đoạn", () => {
    for (const [a, b] of [
      [NEW_YORK, LONDON],
      [LONDON, BEIJING],
      [PARIS, BRUSSELS],
    ] as const) {
      expect(build2DRouteGeometry(a, b)).toHaveLength(1);
    }
  });

  it("đường rỗng hoặc một điểm không làm hỏng hàm", () => {
    expect(splitAntimeridian([])).toEqual([]);
    expect(splitAntimeridian([TOKYO])).toEqual([[TOKYO]]);
  });
});

describe("hành lang ngắn", () => {
  it("Paris → Brussels vẽ thẳng, không cong vô nghĩa", () => {
    const [segment] = build2DRouteGeometry(PARIS, BRUSSELS);
    expect(segment).toHaveLength(2);
  });

  it("hành lang dài vẫn được lấy mẫu để có độ cong", () => {
    const [segment] = build2DRouteGeometry(NEW_YORK, LONDON);
    expect(segment.length).toBeGreaterThan(10);
  });
});

describe("không dùng độ cao", () => {
  it("mọi toạ độ chỉ có hai thành phần", () => {
    for (const segment of build2DRouteGeometry(TOKYO, LOS_ANGELES)) {
      for (const position of segment) expect(position).toHaveLength(2);
    }
  });
});
