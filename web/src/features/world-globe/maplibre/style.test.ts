import { describe, expect, it } from "vitest";
import { COUNTRIES, splitRingAtAntimeridian } from "./style";

type Ring = [number, number][];

function outerRings(): Ring[] {
  return COUNTRIES.features.flatMap((f) =>
    f.geometry.type === "Polygon"
      ? [(f.geometry as GeoJSON.Polygon).coordinates[0] as Ring]
      : (f.geometry as GeoJSON.MultiPolygon).coordinates.map((p) => p[0] as Ring),
  );
}

describe("basemap GeoJSON", () => {
  it("giải mã ra polygon quốc gia hợp lệ", () => {
    expect(COUNTRIES.features.length).toBeGreaterThan(50);
    // Mọi toạ độ phải nằm trong dải hợp lệ; sai ở đây thì MapLibre vẽ ra trống.
    for (const ring of outerRings().slice(0, 20)) {
      for (const [lon, lat] of ring) {
        expect(Number.isFinite(lon) && Number.isFinite(lat)).toBe(true);
        expect(Math.abs(lon)).toBeLessThanOrEqual(180.5);
        expect(Math.abs(lat)).toBeLessThanOrEqual(90.5);
      }
    }
  });

  it("không còn vòng nào vắt ngang kinh tuyến 180° ở vĩ độ Mercator vẽ được", () => {
    // Cạnh nhảy 360° kinh độ bị Mercator vẽ thành một đường ngang hết bản đồ.
    // Nam Cực được miễn (mọi thứ dưới 80°N): cạnh khép vòng của nó chạy sát mép
    // dưới cùng của phép chiếu, và bỏ cạnh đó đi thì vùng tô Nam Cực hở.
    const offenders: number[] = [];
    for (const ring of outerRings()) {
      for (let i = 1; i < ring.length; i++) {
        if (Math.abs(ring[i][0] - ring[i - 1][0]) > 180 && ring[i][1] > -80) {
          offenders.push(ring[i][1]);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("splitRingAtAntimeridian", () => {
  it("trả nguyên vòng không vắt qua kinh tuyến 180°", () => {
    const ring: Ring = [
      [10, 10],
      [20, 10],
      [20, 20],
      [10, 10],
    ];
    expect(splitRingAtAntimeridian(ring)).toEqual([ring]);
  });

  it("tách vòng bị Natural Earth cắt sẵn tại ±180 thành hai vòng khép kín", () => {
    // Hình dạng của Chukotka: phần đại lục chạm mép +180, nhảy sang −180, chạy
    // tiếp rồi nhảy về để khép vòng.
    const ring: Ring = [
      [170, 60],
      [180, 65],
      [-180, 65],
      [-170, 66],
      [-180, 68],
      [180, 68],
      [170, 62],
      [170, 60],
    ];
    const parts = splitRingAtAntimeridian(ring);
    expect(parts).toHaveLength(2);
    for (const part of parts) {
      expect(part[0]).toEqual(part[part.length - 1]);
      const lons = part.map(([lon]) => lon);
      expect(Math.max(...lons) - Math.min(...lons)).toBeLessThanOrEqual(180);
    }
    // Mảnh đại lục nằm ở đông bán cầu, mảnh còn lại ở tây.
    expect(parts.some((p) => p.every(([lon]) => lon >= 0))).toBe(true);
    expect(parts.some((p) => p.every(([lon]) => lon <= 0))).toBe(true);
  });

  it("giữ nguyên vòng chỉ có một cạnh vắt ngang, như Nam Cực", () => {
    // Một bước nhảy duy nhất: đoạn cuối nối tiếp đoạn đầu nên ghép lại vẫn là
    // một vòng, cạnh dọc vĩ tuyến −90 được giữ vì đó là biên thật của vùng tô.
    const ring: Ring = [
      [-180, -85],
      [0, -80],
      [180, -85],
      [180, -90],
      [-180, -90],
      [-180, -85],
    ];
    const parts = splitRingAtAntimeridian(ring);
    expect(parts).toHaveLength(1);
    expect(parts[0][0]).toEqual(parts[0][parts[0].length - 1]);
  });
});
