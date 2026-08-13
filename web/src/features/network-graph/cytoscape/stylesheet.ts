import type { NodeSingular, StylesheetStyle } from "cytoscape";

import { C } from "../../../design/palette";

/**
 * Luật thị giác của đồ thị điều tra.
 *
 * Hai luật chi phối toàn bộ file này:
 *
 *  1. **Màu mã hoá RỦI RO, hình mã hoá LOẠI THỰC THỂ.** Bản cũ gán cho mỗi loại
 *     thực thể một màu bão hoà riêng — sáu màu mạnh cạnh nhau, và câu hỏi đầu
 *     tiên của analyst ("rủi ro nằm ở đâu?") không trả lời được bằng cách nhìn.
 *     Giờ chỉ có bốn màu: trung tính, đáng ngờ, nghiêm trọng, đang chọn.
 *  2. **Nhãn là thứ phải xin mới có.** Mặc định chỉ đỉnh quan trọng hoặc rủi ro
 *     cao mới có nhãn; cạnh thì không có nhãn nào. Phần còn lại hiện khi hover
 *     hoặc khi được chọn. Đây là lý do màn hình cũ rối: mọi đỉnh đều mang tên +
 *     vai trò + số tiền, và 30 đỉnh thành 90 dòng chữ chồng lên nhau.
 *
 * Trạng thái được biểu diễn bằng class chứ không bằng cách dựng lại stylesheet:
 * `cy.batch()` bật/tắt class là thao tác rẻ, còn thay stylesheet thì Cytoscape
 * dựng lại toàn bộ renderer.
 */

/** Bán kính theo tier — tầm quan trọng nghiệp vụ, không phải bậc của đỉnh. */
const TIER_SIZE: Record<number, number> = { 1: 46, 2: 32, 3: 22 };

/**
 * Hình theo loại thực thể (§19).
 *
 * Cytoscape không có "hexagon" nên `polygon` với `shape-polygon-points` là cách
 * duy nhất; chỉ dùng cho VASP vì đó là loại thực thể duy nhất mà việc phân biệt
 * ngay lập tức có giá trị điều tra (cổng ra khỏi hệ thống ngân hàng).
 */
const HEXAGON = "-1 0 -0.5 -0.87 0.5 -0.87 1 0 0.5 0.87 -0.5 0.87";

export function buildStylesheet(): StylesheetStyle[] {
  return [
    // ---------------------------------------------------------------
    // Đỉnh — nền chung
    // ---------------------------------------------------------------
    {
      selector: "node",
      style: {
        "background-color": C.elev,
        "border-width": 1.5,
        "border-color": C.lineStrong,
        width: (n: NodeSingular) => TIER_SIZE[(n.data("tier") as number) ?? 3] ?? 22,
        height: (n: NodeSingular) => TIER_SIZE[(n.data("tier") as number) ?? 3] ?? 22,
        shape: "ellipse",
        label: "",
        "font-family": "Geist, Inter, system-ui, sans-serif",
        "font-size": 11,
        "font-weight": 500,
        color: C.inkMid,
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-max-width": "96px",
        "text-wrap": "ellipsis",
        "overlay-opacity": 0,
        "transition-property": "opacity, border-color, background-color, border-width",
        "transition-duration": 140,
      },
    },

    // Hình theo loại thực thể. Đường viền đứt nghĩa là "chưa xác định được
    // danh tính" — nền tảng và thực thể không rõ loại.
    { selector: 'node[etype = "account"]', style: { shape: "ellipse" } },
    { selector: 'node[etype = "organisation"], node[etype = "org"]', style: { shape: "round-rectangle" } },
    {
      selector: 'node[etype = "vasp"]',
      style: { shape: "polygon", "shape-polygon-points": HEXAGON },
    },
    { selector: 'node[etype = "wallet"]', style: { shape: "diamond" } },
    { selector: 'node[etype = "device"]', style: { shape: "rectangle" } },
    { selector: 'node[etype = "person"]', style: { shape: "ellipse" } },
    {
      selector: 'node[etype = "platform"], node[etype = "project"], node[etype = "token"]',
      style: { shape: "round-rectangle", "border-style": "dashed" },
    },
    { selector: 'node[etype = "contract"]', style: { shape: "diamond" } },

    // ---------------------------------------------------------------
    // Đỉnh — màu theo rủi ro (§20, §21)
    // ---------------------------------------------------------------
    {
      selector: "node.risk-warn",
      style: { "border-color": C.warn, "background-color": "#221B0E", "border-width": 2 },
    },
    {
      selector: "node.risk-crit",
      style: { "border-color": C.risk, "background-color": "#2A1116", "border-width": 2.5 },
    },
    // Hard negative: thực thể hợp pháp cố ý đưa vào để đo dương tính giả. Phải
    // nhìn ra được nó *không* thuộc mạch chính, nếu không analyst sẽ điều tra
    // nhầm và bộ đo mất ý nghĩa.
    {
      selector: "node.negative",
      style: { "border-style": "dotted", "border-color": C.inkDim, "background-color": C.sunken },
    },

    // Cụm đang thu gọn: một khối, kèm số thành viên. Không phải hộp nét đứt to
    // như bản cũ — hộp đó chiếm diện tích bằng cả cụm mà không mang thông tin.
    {
      selector: "node.collapsed-cluster",
      style: {
        shape: "round-rectangle",
        width: 58,
        height: 40,
        "background-color": C.panel,
        "border-color": C.lineStrong,
        "border-width": 1.5,
        label: "data(clusterLabel)",
        "text-valign": "bottom",
        "font-size": 10,
        color: C.inkSoft,
      },
    },
    {
      selector: "node.collapsed-cluster > *",
      style: { display: "none" },
    },

    // Cụm đang mở là compound node: chỉ một khung rất nhạt bao quanh, đúng
    // tinh thần "ranh giới cụm phải mờ" (§21).
    {
      selector: "node.cluster-parent",
      style: {
        shape: "round-rectangle",
        "background-color": C.side,
        "background-opacity": 0.5,
        "border-color": C.line,
        "border-width": 1,
        "border-style": "dashed",
        label: "data(clusterLabel)",
        "text-valign": "top",
        "text-halign": "center",
        "text-margin-y": -4,
        "font-size": 9.5,
        "font-weight": 600,
        color: C.inkDim,
        padding: "18px",
      },
    },

    // ---------------------------------------------------------------
    // Nhãn đỉnh — hiện theo mức chi tiết (§16, §17)
    // ---------------------------------------------------------------
    // `.labelled` do lớp semantic zoom gắn vào; hover và selection ghi đè.
    { selector: "node.labelled", style: { label: "data(short)" } },
    {
      selector: "node.hovered, node.selected",
      style: { label: "data(label)", color: C.inkHi, "font-weight": 600, "z-index": 30 },
    },
    {
      selector: "node.selected",
      style: {
        "border-color": C.primary,
        "border-width": 3,
        "background-color": "#0C2620",
      },
    },
    // Đỉnh nằm trên đường tiền đang xem: viền đỏ nhưng KHÔNG to thêm, để không
    // cạnh tranh với đỉnh đang chọn.
    { selector: "node.on-path", style: { "border-color": C.risk, "border-width": 2.5 } },

    // ---------------------------------------------------------------
    // Cạnh
    // ---------------------------------------------------------------
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": C.line,
        "curve-style": "bezier",
        "control-point-step-size": 28,
        // Mũi tên nhỏ — hướng tiền phải đọc được, không phải phải hét lên (§24).
        "target-arrow-shape": "triangle",
        "target-arrow-color": C.line,
        "arrow-scale": 0.6,
        opacity: 0.35,
        label: "",
        "font-family": "JetBrains Mono, ui-monospace, monospace",
        "font-size": 9.5,
        color: C.inkSoft,
        "text-background-color": C.app,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-rotation": "autorotate",
        "transition-property": "opacity, line-color, width",
        "transition-duration": 140,
      },
    },
    // Cạnh dòng tiền nổi hơn cạnh cấu trúc (sở hữu, thiết bị) — đây là thứ tự
    // ưu tiên §21: dòng tiền chính trên, quan hệ thường dưới.
    {
      selector: "edge.money",
      style: { width: 1.6, "line-color": "#2B4358", "target-arrow-color": "#2B4358", opacity: 0.55 },
    },
    // Cạnh suy luận: nét đứt. Analyst phải phân biệt được "quan sát thấy" với
    // "suy ra" mà không cần bấm vào.
    { selector: "edge.inferred", style: { "line-style": "dashed" } },
    { selector: "edge.risk-warn", style: { "line-color": C.warn, "target-arrow-color": C.warn, opacity: 0.75 } },
    { selector: "edge.risk-crit", style: { "line-color": C.risk, "target-arrow-color": C.risk, opacity: 0.9, width: 2.2 } },

    // Nhãn cạnh CHỈ khi được chọn hoặc nằm trên đường tiền đang xem (§18).
    {
      selector: "edge.selected, edge.on-path",
      style: {
        label: "data(edgeLabel)",
        "line-color": C.primary,
        "target-arrow-color": C.primary,
        width: 2.4,
        opacity: 1,
        "z-index": 30,
      },
    },
    {
      selector: "edge.on-path",
      style: { "line-color": C.risk, "target-arrow-color": C.risk },
    },
    { selector: "edge.hovered", style: { opacity: 0.95, width: 2.4 } },

    // Chỗ đứt bằng chứng: chấm chấm, không mũi tên, màu trung tính. Cố ý KHÔNG
    // trông giống bất kỳ quan hệ nào — nó nói "ở đây chúng tôi không quan sát
    // được gì", chứ không nói "ở đây có liên kết".
    {
      selector: "edge.evidence-gap",
      style: {
        "line-style": "dotted",
        "line-color": C.inkDim,
        "target-arrow-shape": "none",
        width: 1.2,
        opacity: 0.4,
        label: "",
      },
    },
    { selector: "edge.evidence-gap.hovered", style: { opacity: 0.8, label: "chưa có liên kết quan sát" } },

    // ---------------------------------------------------------------
    // Focus + context (§12)
    // ---------------------------------------------------------------
    // Không xoá phần không liên quan — làm mờ. Analyst vẫn cần thấy thực thể
    // đang xem nằm ở đâu trong mạng lưới.
    { selector: ".dimmed", style: { opacity: 0.12 } },
    { selector: "node.dimmed", style: { label: "" } },
    { selector: ".neighbour", style: { opacity: 0.9 } },
  ];
}
