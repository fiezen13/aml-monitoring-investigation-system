/**
 * Basemap tối cho bản đồ điều tra AML.
 *
 * Không dùng tile server: ranh giới quốc gia lấy từ gói `world-atlas` đã nằm sẵn
 * trong bundle. Console tuân thủ ngân hàng thường chạy sau mạng chặn Internet ra
 * ngoài, và một bản đồ phải gọi tile mới hiện được là bản đồ không dùng được ở
 * đó. Đổi lại basemap chỉ có đường biên — nhưng đó đúng là thứ §8 yêu cầu:
 * "ocean rất tối, land tối hơn chút, borders subtle, POI off".
 */

import type { Feature, FeatureCollection } from "geojson";
import type { StyleSpecification } from "maplibre-gl";
import topology from "world-atlas/countries-110m.json";

/** Bảng màu lấy từ design token của console (web/tailwind.config.js). */
export const BASEMAP = {
  ocean: "#06111d",
  land: "#102333",
  border: "#29445a",
} as const;

type Ring = [number, number][];

interface Topology {
  transform: { scale: [number, number]; translate: [number, number] };
  arcs: [number, number][][];
  objects: Record<string, { type: string; geometries: TopoGeometry[] }>;
}

interface TopoGeometry {
  type: "Polygon" | "MultiPolygon" | string;
  arcs: number[][] | number[][][];
}

/**
 * Giải mã TopoJSON sang GeoJSON.
 *
 * Tự viết thay vì thêm `topojson-client`: chỉ cần đúng phép giải delta và ghép
 * cung cho Polygon/MultiPolygon, khoảng ba chục dòng, và tránh thêm một phụ
 * thuộc chỉ dùng một lần lúc khởi tạo.
 */
export function decodeTopology(topo: Topology, objectName = "countries"): FeatureCollection {
  const [sx, sy] = topo.transform.scale;
  const [tx, ty] = topo.transform.translate;

  // Toạ độ trong TopoJSON được lưu dạng delta lượng tử hoá.
  const arcs: Ring[] = topo.arcs.map((arc) => {
    let x = 0;
    let y = 0;
    return arc.map(([dx, dy]) => {
      x += dx;
      y += dy;
      return [x * sx + tx, y * sy + ty] as [number, number];
    });
  });

  const ring = (indexes: number[]): Ring => {
    const out: Ring = [];
    for (const index of indexes) {
      // Chỉ số âm nghĩa là dùng cung đó theo chiều ngược, và điểm đầu trùng với
      // điểm cuối của cung trước nên phải bỏ đi.
      const arc = index < 0 ? arcs[~index].slice().reverse() : arcs[index];
      out.push(...(out.length ? arc.slice(1) : arc));
    }
    return out;
  };

  // Một polygon vào, một hoặc nhiều polygon ra (xem splitRingAtAntimeridian).
  const polygon = (indexes: number[][]): Ring[][] => {
    const [outer, ...holes] = indexes.map(ring);
    const parts = splitRingAtAntimeridian(outer);
    // Lỗ chỉ gắn vào mảnh đầu: ở độ phân giải 110m không nước nào vừa có lỗ vừa
    // vắt qua kinh tuyến 180°, nên không cần xét lỗ nằm trong mảnh nào.
    return parts.map((part, index) => (index === 0 ? [part, ...holes] : [part]));
  };

  const object = topo.objects[objectName];
  const features: Feature[] = [];
  for (const geometry of object.geometries) {
    let coordinates: Ring[][] = [];
    if (geometry.type === "Polygon") {
      coordinates = polygon(geometry.arcs as number[][]);
    } else if (geometry.type === "MultiPolygon") {
      coordinates = (geometry.arcs as number[][][]).flatMap(polygon);
    } else {
      continue;
    }
    features.push({
      type: "Feature",
      properties: {},
      geometry: { type: "MultiPolygon", coordinates },
    });
  }
  return { type: "FeatureCollection", features };
}

/**
 * Cắt một vòng polygon tại kinh tuyến ±180°.
 *
 * Natural Earth cắt sẵn các nước vắt qua đường đổi ngày ngay tại ±180 rồi nối
 * hai mép bằng một cạnh duy nhất nhảy 360° kinh độ. Mercator vẽ cạnh đó thành
 * một đường ngang chạy hết chiều rộng bản đồ: phần Chukotka của Nga hiện ra
 * thành một dải sáng vắt ngang Bắc Băng Dương ở khoảng 68–75°B.
 *
 * Cắt vòng tại mỗi bước nhảy sẽ tách phần đại lục và phần bên kia đường đổi
 * ngày thành hai vòng riêng. Vòng khép kín nên đoạn cuối nối tiếp đoạn đầu và
 * phải ghép lại làm một trước khi khép.
 *
 * Nam Cực là trường hợp chỉ có đúng một bước nhảy — cạnh chạy dọc vĩ tuyến −90.
 * Ghép đầu-cuối trả về đúng một vòng như cũ, tức là hàm này không đụng tới nó:
 * cạnh ấy là biên thật của vùng tô, và nó nằm dưới giới hạn Mercator nên không
 * bao giờ hiện lên.
 */
export function splitRingAtAntimeridian(ring: Ring): Ring[] {
  const cuts: number[] = [];
  for (let i = 1; i < ring.length; i++) {
    if (Math.abs(ring[i][0] - ring[i - 1][0]) > 180) cuts.push(i);
  }
  if (!cuts.length) return [ring];

  const chains: Ring[] = [];
  let start = 0;
  for (const cut of cuts) {
    chains.push(ring.slice(start, cut));
    start = cut;
  }
  chains.push(ring.slice(start));

  // Điểm đầu vòng trùng điểm cuối, nên đoạn cuối và đoạn đầu vốn là một.
  const tail = chains.pop();
  if (tail) chains[0] = tail.concat(chains[0].slice(1));

  return chains
    .filter((chain) => chain.length >= 3)
    .map((chain) => {
      const first = chain[0];
      const last = chain[chain.length - 1];
      return first[0] === last[0] && first[1] === last[1] ? chain : [...chain, first];
    });
}

export const COUNTRIES = decodeTopology(topology as unknown as Topology);

/**
 * Style nền: đại dương, đất liền, đường biên. Không nhãn địa lý, không POI,
 * không đường sá — tín hiệu AML mới là thứ cần đọc, phần còn lại là bối cảnh.
 */
export function darkBasemapStyle(): StyleSpecification {
  return {
    version: 8,
    // Cố ý KHÔNG khai báo `glyphs`: style spec đòi kiểu chuỗi, đặt undefined làm
    // style hỏng và sự kiện `load` không bao giờ bắn — bản đồ kẹt mãi ở trạng
    // thái đang dựng. Không glyphs nghĩa là basemap không có nhãn, đúng ý đồ:
    // nhãn duy nhất trên bản đồ là của node AML.
    sources: {
      countries: { type: "geojson", data: COUNTRIES },
    },
    layers: [
      { id: "ocean", type: "background", paint: { "background-color": BASEMAP.ocean } },
      {
        id: "land",
        type: "fill",
        source: "countries",
        paint: { "fill-color": BASEMAP.land },
      },
      {
        id: "border",
        type: "line",
        source: "countries",
        paint: {
          "line-color": BASEMAP.border,
          "line-width": 0.6,
          "line-opacity": 0.55,
        },
      },
    ],
  };
}

/**
 * Khung nhìn thế giới cho nghiệp vụ AML.
 *
 * Cắt bớt vùng cực nam: Nam Cực gần như không mang thông tin cho giám sát dòng
 * tiền, mà lại chiếm rất nhiều diện tích trong phép chiếu Mercator.
 */
export const WORLD_BOUNDS: [[number, number], [number, number]] = [
  [-180, -60],
  [180, 82],
];
