import type { Band, LayoutKey, RenderGraph, RenderNode } from "../types/graph.types";
import { STAGE_INDEX } from "../types/graph.types";

/**
 * Bốn cách xếp đồ thị. Mặc định bắt buộc là `flow`.
 *
 * Force layout cũ dồn mọi thứ thành một quả cầu ở giữa — đẹp nhưng không đọc
 * được. Layout mặc định giờ là dạng phân tầng trái → phải theo đúng thứ tự các
 * chặng của dòng tiền, vì đó chính là câu chuyện analyst cần thấy trước.
 */

const COL_W = 252;

/**
 * Khoảng cách dọc giữa hai đỉnh cùng cột.
 *
 * Phải chứa được cả đường kính đỉnh lẫn khối nhãn bên dưới. Nhãn vẽ ở kích
 * thước màn hình cố định nên chỗ nó chiếm trong toạ độ world *tăng lên* khi
 * đồ thị bị thu nhỏ — đó là lý do bản trước (82) bị chồng chữ ở mức phóng 0.55.
 */
const ROW_H = 146;

/** Băng phụ dùng hàng thấp hơn: đỉnh tier 3 nhỏ và không có dòng nhãn phụ. */
const SUPPORT_ROW_H = 84;

/** Số đỉnh tối đa xếp ngang trong một nhóm ở băng phụ. */
const SUPPORT_PER_ROW = 3;

/** Số hàng tối đa của băng chính trước khi cột được tách làm đôi. */
const MAX_PRIMARY_ROWS = 6;

/**
 * Khoảng cách giữa ba băng, tính theo bội số ROW_H.
 *
 * Kéo sát lại so với bản trước: băng ngữ cảnh phải *thuộc về* cùng một bức
 * tranh với mạch tiền chính. Đẩy chúng ra xa thì trông như hai đồ thị rời nhau
 * và ở giữa là một vùng trống lớn không mang thông tin gì.
 */
const BAND_GAP: Record<Band, number> = { primary: 0, support: 0.42, control: 0.5 };

const BAND_ORDER: Band[] = ["primary", "support", "control"];

/**
 * Nén các chặng về cột liên tiếp.
 *
 * `STAGE_INDEX` có 9 chặng nhưng dữ liệu thật hiếm khi dùng hết. Nhân thẳng
 * chỉ số chặng với bề rộng cột sẽ chừa lại những cột trống cho các chặng không
 * có đỉnh nào, kéo hộp bao của đồ thị rộng ra vô ích — và vì `fit` chọn mức
 * phóng theo cạnh dài nhất, mỗi cột trống là một lần cả đồ thị bị thu nhỏ lại.
 */
function occupiedColumns(nodes: RenderNode[]): Map<number, number> {
  const used = [...new Set(nodes.map((n) => STAGE_INDEX[n.stage] ?? 0))].sort((a, b) => a - b);
  return new Map(used.map((stageIdx, i) => [stageIdx, i]));
}

function groupByColumn(nodes: RenderNode[], compact: Map<number, number>): Map<number, RenderNode[]> {
  const cols = new Map<number, RenderNode[]>();
  nodes.forEach((n) => {
    const c = compact.get(STAGE_INDEX[n.stage] ?? 0) ?? 0;
    const list = cols.get(c);
    if (list) list.push(n);
    else cols.set(c, [n]);
  });
  return cols;
}

/**
 * Xếp theo chặng, trái → phải.
 *
 * Ba lượt trọng tâm (barycenter) để giảm cạnh cắt nhau: mỗi node được kéo về
 * gần trung bình vị trí của các node nó nối tới ở cột liền trước. Đây là mẹo
 * kinh điển của Sugiyama, ba lượt là đủ cho quy mô vài trăm đỉnh.
 */
function investigationFlow(graph: RenderGraph): void {
  const compact = occupiedColumns(graph.nodes);
  const cols = groupByColumn(graph.nodes, compact);
  const colKeys = [...cols.keys()].sort((a, b) => a - b);
  const columnOf = (n: RenderNode) => compact.get(STAGE_INDEX[n.stage] ?? 0) ?? 0;

  // Xếp ban đầu: theo băng, rồi gom thành viên cùng cụm cạnh nhau, rồi rủi ro.
  colKeys.forEach((c) => {
    const list = cols.get(c) as RenderNode[];
    list.sort((a, b) => {
      const ba = BAND_ORDER.indexOf(a.band) - BAND_ORDER.indexOf(b.band);
      if (ba !== 0) return ba;
      const ca = (a.parentClusterId ?? "").localeCompare(b.parentClusterId ?? "");
      if (ca !== 0) return ca;
      return b.risk - a.risk;
    });
  });

  /**
   * Xếp lưới ngang cho một nhóm ở băng phụ, so le theo cột.
   *
   * So le là mấu chốt: nhãn vẽ ở kích thước màn hình nên bề rộng chữ không co
   * theo mức phóng, và ba cái "Thiết bị A/B/C" đặt ngang hàng sẽ dính vào nhau
   * ở mọi mức phóng thực tế. Đẩy cột lẻ xuống một nấc thì hai nhãn kề nhau nằm
   * ở hai độ cao khác nhau và không còn chạm.
   */
  const placeGrid = (group: RenderNode[], baseX: number, baseY: number): number => {
    const perRow = Math.min(SUPPORT_PER_ROW, group.length);
    group.forEach((n, i) => {
      const col = i % perRow;
      const row = Math.floor(i / perRow);
      n.x = baseX + (col - (perRow - 1) / 2) * (COL_W * 0.46);
      n.y = baseY + row * SUPPORT_ROW_H + (col % 2) * (SUPPORT_ROW_H * 0.42);
    });
    // Chừa chỗ cho cả độ lệch so le lẫn nhãn của đường bao nhóm kế tiếp — thiếu
    // thì hai hull dính vào nhau và hai nhãn đè lên nhau.
    return Math.ceil(group.length / perRow) * SUPPORT_ROW_H + SUPPORT_ROW_H * 1.05;
  };

  const groupsOf = (arr: RenderNode[]): RenderNode[][] => {
    const groups = new Map<string, RenderNode[]>();
    arr.forEach((n) => {
      const key = n.parentClusterId ?? n.id;
      const g = groups.get(key);
      if (g) g.push(n);
      else groups.set(key, [n]);
    });
    return [...groups.values()];
  };

  const place = () => {
    const bandsByCol = new Map<number, Map<Band, RenderNode[]>>();
    const supportEnd = new Map<number, number>();

    // Lượt 1 — băng chính căn quanh trục y = 0, băng phụ xếp ngay bên dưới.
    colKeys.forEach((c) => {
      const list = cols.get(c) as RenderNode[];
      const byBand = new Map<Band, RenderNode[]>();
      list.forEach((n) => {
        const arr = byBand.get(n.band);
        if (arr) arr.push(n);
        else byBand.set(n.band, [n]);
      });
      bandsByCol.set(c, byBand);

      // Cột quá cao thì tách thành cột con.
      //
      // Mười hai mule xếp thành một cột dọc cao gần 1800 đơn vị, trong khi cả
      // đồ thị chỉ rộng chừng 2000 — `fit` buộc phải thu theo chiều cao và mọi
      // thứ khác teo lại theo. Chia đôi cột giữ nguyên thông tin mà hạ chiều cao
      // một nửa.
      const primary = byBand.get("primary") ?? [];
      const lanes = Math.ceil(primary.length / MAX_PRIMARY_ROWS);
      const rows = Math.ceil(primary.length / lanes);
      primary.forEach((n, i) => {
        const lane = Math.floor(i / rows);
        const row = i % rows;
        n.x = c * COL_W + (lane - (lanes - 1) / 2) * (COL_W * 0.42);
        n.y = (row - (rows - 1) / 2) * ROW_H;
      });

      let cursor = (rows ? (rows - 1) / 2 : 0) * ROW_H + BAND_GAP.support * ROW_H;
      groupsOf(byBand.get("support") ?? []).forEach((group) => {
        cursor += placeGrid(group, c * COL_W, cursor);
      });
      supportEnd.set(c, cursor);
    });

    // Lượt 2 — đối chứng hợp pháp căn về một đường ngang chung cho mọi cột.
    // Để mỗi cột tự quyết định độ cao thì ba đỉnh đối chứng rơi vào ba độ cao
    // khác nhau, kéo hộp bao của cả đồ thị dài thêm mà không thêm thông tin gì.
    const baseline = Math.max(...colKeys.map((c) => supportEnd.get(c) ?? 0)) + BAND_GAP.control * ROW_H;
    colKeys.forEach((c) => {
      const control = bandsByCol.get(c)?.get("control") ?? [];
      if (!control.length) return;
      groupsOf(control).forEach((group, gi) => {
        placeGrid(group, c * COL_W, baseline + gi * SUPPORT_ROW_H);
      });
    });
  };

  place();

  const adj = new Map<string, string[]>();
  graph.edges.forEach((e) => {
    if (!adj.has(e.t)) adj.set(e.t, []);
    if (!adj.has(e.s)) adj.set(e.s, []);
    (adj.get(e.t) as string[]).push(e.s);
    (adj.get(e.s) as string[]).push(e.t);
  });

  for (let pass = 0; pass < 3; pass++) {
    colKeys.forEach((c) => {
      const list = cols.get(c) as RenderNode[];
      const bary = new Map<string, number>();
      list.forEach((n) => {
        const nbrs = (adj.get(n.id) ?? [])
          .map((id) => graph.byId[id])
          .filter((m): m is RenderNode => !!m && columnOf(m) !== c);
        bary.set(n.id, nbrs.length ? nbrs.reduce((s, m) => s + m.y, 0) / nbrs.length : n.y);
      });
      list.sort((a, b) => {
        const ba = BAND_ORDER.indexOf(a.band) - BAND_ORDER.indexOf(b.band);
        if (ba !== 0) return ba;
        // Thành viên cùng cụm phải dính nhau, nếu không hull sẽ trùm lên node lạ.
        const ca = (a.parentClusterId ?? "").localeCompare(b.parentClusterId ?? "");
        if (ca !== 0) return ca;
        return (bary.get(a.id) ?? 0) - (bary.get(b.id) ?? 0);
      });
    });
    place();
  }
}

/** Force cổ điển — giữ lại cho analyst muốn nhìn cấu trúc thô. */
function forceLayout(graph: RenderGraph): void {
  const N = graph.nodes;
  if (!N.length) return;
  N.forEach((n, i) => {
    const a = (i / N.length) * Math.PI * 2;
    const R = 260;
    n.x = Math.cos(a) * R * (0.45 + ((i * 37) % 53) / 53 * 0.55);
    n.y = Math.sin(a) * R * (0.45 + ((i * 29) % 47) / 47 * 0.55);
  });

  const iterations = N.length > 220 ? 140 : 300;
  for (let it = 0; it < iterations; it++) {
    const k = it < iterations * 0.6 ? 1 : 0.35;
    for (let i = 0; i < N.length; i++) {
      for (let j = i + 1; j < N.length; j++) {
        const a = N[i];
        const b = N[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        const d2 = dx * dx + dy * dy || 0.01;
        if (d2 > 160000) continue;
        const f = (3400 / d2) * k;
        const d = Math.sqrt(d2);
        dx /= d;
        dy /= d;
        a.x += dx * f;
        a.y += dy * f;
        b.x -= dx * f;
        b.y -= dy * f;
      }
    }
    graph.edges.forEach((e) => {
      const a = graph.byId[e.s];
      const b = graph.byId[e.t];
      if (!a || !b) return;
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      const d = Math.hypot(dx, dy) || 1;
      const f = (d - 115) * 0.014 * k;
      dx /= d;
      dy /= d;
      a.x += dx * f;
      a.y += dy * f;
      b.x -= dx * f;
      b.y -= dy * f;
    });
  }
}

/** Cây phân cấp: cùng chặng thì xếp dọc, nhưng giãn theo bậc của đỉnh. */
function hierarchy(graph: RenderGraph): void {
  investigationFlow(graph);
  const cols = groupByColumn(graph.nodes, occupiedColumns(graph.nodes));
  cols.forEach((list) => {
    const total = list.reduce((s, n) => s + Math.max(1, n.count), 0);
    let y = -(total * ROW_H) / 2;
    list.forEach((n) => {
      const h = Math.max(1, n.count) * ROW_H;
      n.y = y + h / 2;
      y += h;
    });
  });
}

/** Mỗi cụm/chặng thành một đảo riêng, xếp vòng tròn. */
function community(graph: RenderGraph): void {
  const groups = new Map<string, RenderNode[]>();
  graph.nodes.forEach((n) => {
    const key = n.parentClusterId ?? n.cluster?.id ?? n.stage;
    const arr = groups.get(key);
    if (arr) arr.push(n);
    else groups.set(key, [n]);
  });

  const keys = [...groups.keys()];
  const ring = Math.max(340, keys.length * 78);
  keys.forEach((key, gi) => {
    const list = groups.get(key) as RenderNode[];
    const ang = (gi / keys.length) * Math.PI * 2;
    const cx = Math.cos(ang) * ring;
    const cy = Math.sin(ang) * ring * 0.72;
    const r = 34 + list.length * 8.5;
    list.forEach((n, i) => {
      const a = (i / Math.max(1, list.length)) * Math.PI * 2;
      n.x = cx + Math.cos(a) * r;
      n.y = cy + Math.sin(a) * r;
    });
  });
}

export function applyLayout(graph: RenderGraph, layout: LayoutKey): void {
  if (!graph.nodes.length) return;
  switch (layout) {
    case "force":
      forceLayout(graph);
      break;
    case "hierarchy":
      hierarchy(graph);
      break;
    case "community":
      community(graph);
      break;
    case "flow":
    default:
      investigationFlow(graph);
  }
}

/** Nhãn cột hiển thị phía trên đồ thị ở chế độ flow. */
export function columnPositions(graph: RenderGraph): { x: number; stage: string }[] {
  const compact = occupiedColumns(graph.nodes);
  const seen = new Map<number, string>();
  graph.nodes.forEach((n) => {
    const c = compact.get(STAGE_INDEX[n.stage] ?? 0) ?? 0;
    if (!seen.has(c)) seen.set(c, n.stage);
  });
  return [...seen.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([c, stage]) => ({ x: c * COL_W, stage }));
}
