import type { EdgeSingular, NodeSingular, StylesheetStyle } from "cytoscape";

import { cytoscapeTheme as T } from "../../../design/adapters/cytoscapeTheme";

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
        "background-color": T.node.fill,
        "border-width": 1.5,
        "border-color": T.node.border,
        width: (n: NodeSingular) => TIER_SIZE[(n.data("tier") as number) ?? 3] ?? 22,
        height: (n: NodeSingular) => TIER_SIZE[(n.data("tier") as number) ?? 3] ?? 22,
        shape: "ellipse",
        label: "",
        "font-family": T.font.sans,
        "font-size": 11,
        "font-weight": 500,
        color: T.node.label,
        "text-valign": "bottom",
        "text-margin-y": 5,
        "text-max-width": "96px",
        "text-wrap": "ellipsis",
        "overlay-opacity": 0,
        "transition-property": "opacity, border-color, background-color, border-width",
        "transition-duration": T.transitionMs,
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
      style: { "border-color": T.tone.warn, "background-color": T.node.fillWarn, "border-width": 2 },
    },
    {
      selector: "node.risk-crit",
      style: { "border-color": T.tone.crit, "background-color": T.node.fillCrit, "border-width": 2.5 },
    },
    // Hard negative: thực thể hợp pháp cố ý đưa vào để đo dương tính giả. Phải
    // nhìn ra được nó *không* thuộc mạch chính, nếu không analyst sẽ điều tra
    // nhầm và bộ đo mất ý nghĩa.
    {
      selector: "node.negative",
      style: { "border-style": "dotted", "border-color": T.tone.muted, "background-color": T.node.fillMuted },
    },

    // Cụm đang thu gọn: một khối, kèm số thành viên. Không phải hộp nét đứt to
    // như bản cũ — hộp đó chiếm diện tích bằng cả cụm mà không mang thông tin.
    {
      selector: "node.collapsed-cluster",
      style: {
        shape: "round-rectangle",
        width: 58,
        height: 40,
        "background-color": T.node.cluster,
        "border-color": T.node.border,
        "border-width": 1.5,
        label: "data(clusterLabel)",
        "text-valign": "bottom",
        "font-size": 10,
        color: T.node.label,
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
        "background-color": T.node.clusterParent,
        "background-opacity": 0.5,
        "border-color": T.edge.base,
        "border-width": 1,
        "border-style": "dashed",
        label: "data(clusterLabel)",
        "text-valign": "top",
        "text-halign": "center",
        "text-margin-y": -4,
        "font-size": 9.5,
        "font-weight": 600,
        color: T.tone.muted,
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
      style: { label: "data(label)", color: T.node.labelActive, "font-weight": 600, "z-index": 30 },
    },
    {
      selector: "node.selected",
      style: {
        "border-color": T.tone.selected,
        "border-width": 3,
        "background-color": T.node.fillSelected,
        width: 52,
        height: 52,
        "underlay-color": T.tone.selected,
        "underlay-opacity": 0.12,
        "underlay-padding": 7,
      },
    },
    // Đỉnh nằm trên đường tiền đang xem: viền đỏ nhưng KHÔNG to thêm, để không
    // cạnh tranh với đỉnh đang chọn.
    { selector: "node.on-path", style: { "border-color": T.tone.crit, "border-width": 2.5 } },

    // ---------------------------------------------------------------
    // Cạnh
    // ---------------------------------------------------------------
    {
      selector: "edge",
      style: {
        width: 1,
        "line-color": T.edge.base,
        "curve-style": "bezier",
        "control-point-step-size": 28,
        // Mũi tên phải đọc được ở mức phóng mặc định.
        //
        // Bản trước đặt arrow-scale 0.6 và opacity 0.35 với lý do "hướng tiền
        // phải đọc được, không phải hét lên". Dùng thật thì ngược lại: chuyên
        // viên phải phóng to mới thấy mũi tên, và câu hỏi đầu tiên khi mở đồ thị
        // — tiền vào hay tiền ra — không trả lời được. Hướng là thông tin bắt
        // buộc của một đồ thị dòng tiền, không phải chi tiết trang trí.
        "target-arrow-shape": "triangle",
        "target-arrow-color": T.edge.base,
        "arrow-scale": 1.3,
        opacity: 0.55,
        label: "",
        "font-family": T.font.mono,
        "font-size": 9.5,
        color: T.node.label,
        "text-background-color": T.edge.labelBackground,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-rotation": "autorotate",
        "transition-property": "opacity, line-color, width",
        "transition-duration": T.transitionMs,
      },
    },
    // Cạnh dòng tiền nổi hơn cạnh cấu trúc (sở hữu, thiết bị) — đây là thứ tự
    // ưu tiên §21: dòng tiền chính trên, quan hệ thường dưới.
    {
      selector: "edge.money",
      style: {
        // Log/capped hierarchy theo số giao dịch thật. Một cạnh 100 giao dịch
        // không được dày gấp 100 lần cạnh 1 giao dịch.
        width: (edge: EdgeSingular) => {
          const count = Number(edge.data("txCount") ?? 0);
          if (count >= 50) return 3.2;
          if (count >= 15) return 2.4;
          if (count >= 5) return 1.8;
          return count >= 2 ? 1.4 : 1;
        },
        "line-color": T.edge.money,
        "target-arrow-color": T.edge.money,
        // Cạnh dòng tiền là lớp mang thông tin hướng; nó phải nổi hơn cạnh cấu
        // trúc chứ không chìm cùng một mức mờ.
        "arrow-scale": 1.5,
        opacity: 0.85,
      },
    },
    // Cạnh suy luận: nét đứt. Analyst phải phân biệt được "quan sát thấy" với
    // "suy ra" mà không cần bấm vào.
    { selector: "edge.inferred", style: { "line-style": "dashed" } },
    { selector: "edge.device-link", style: { "line-style": "dotted" } },
    {
      selector: "edge.risk-warn",
      style: { "line-color": T.tone.warn, "target-arrow-color": T.tone.warn, opacity: 0.9, "arrow-scale": 1.5 },
    },
    {
      selector: "edge.risk-crit",
      style: {
        "line-color": T.tone.crit,
        "target-arrow-color": T.tone.crit,
        opacity: 1,
        width: 2.6,
        "arrow-scale": 1.7,
      },
    },

    // Hướng tiền so với đỉnh đang chọn. Xanh lá = chảy VÀO, hổ phách = chảy RA.
    // Đặt trước khối .selected/.on-path để đường tiền đang xem vẫn thắng về màu.
    {
      selector: "edge.flow-in",
      style: {
        "line-color": T.tone.verified,
        "target-arrow-color": T.tone.verified,
        opacity: 1,
        width: 2.6,
        "arrow-scale": 1.6,
        "z-index": 20,
      },
    },
    {
      selector: "edge.flow-out",
      style: {
        "line-color": T.tone.warn,
        "target-arrow-color": T.tone.warn,
        opacity: 1,
        width: 2.6,
        "arrow-scale": 1.6,
        "z-index": 20,
      },
    },

    // Nhãn cạnh CHỈ khi được chọn hoặc nằm trên đường tiền đang xem (§18).
    {
      selector: "edge.selected, edge.on-path",
      style: {
        label: "data(edgeLabel)",
        "line-color": T.tone.selected,
        "target-arrow-color": T.tone.selected,
        width: 4,
        opacity: 1,
        "arrow-scale": 1.8,
        "z-index": 30,
      },
    },
    {
      selector: "edge.on-path",
      style: { "line-color": T.tone.crit, "target-arrow-color": T.tone.crit },
    },
    { selector: "edge.hovered", style: { opacity: 0.95, width: 2.4 } },
    {
      selector: "edge.replaying",
      style: {
        opacity: 1,
        width: 3.2,
        "line-color": T.tone.selected,
        "target-arrow-color": T.tone.selected,
        "line-style": "dashed",
        "line-dash-pattern": [9, 5],
        "z-index": 40,
      },
    },
    {
      selector: "node.replay-node",
      style: { "border-color": T.tone.selected, "border-width": 3, "background-color": T.node.fillSelected },
    },

    // Chỗ đứt bằng chứng: chấm chấm, không mũi tên, màu trung tính. Cố ý KHÔNG
    // trông giống bất kỳ quan hệ nào — nó nói "ở đây chúng tôi không quan sát
    // được gì", chứ không nói "ở đây có liên kết".
    {
      selector: "edge.evidence-gap",
      style: {
        "line-style": "dotted",
        "line-color": T.tone.muted,
        "target-arrow-shape": "none",
        width: 1.2,
        opacity: 0.4,
        label: "",
      },
    },
    { selector: "edge.evidence-gap.hovered", style: { opacity: 0.8, label: "chưa có liên kết quan sát" } },

    // Evidence là một lớp đọc trên bố cục hiện tại: quan sát trực tiếp rõ,
    // suy luận đứt nét, thiết bị chấm, hard-negative xanh trầm. Không dữ liệu
    // nào bị đổi hoặc được tạo thêm để phục vụ cách vẽ này.
    {
      selector: "edge.evidence-mode.observed",
      style: { opacity: 0.72, width: 1.8, "line-color": T.tone.selected, "target-arrow-color": T.tone.selected },
    },
    { selector: "edge.evidence-mode.inferred", style: { opacity: 0.78, width: 1.6, "line-style": "dashed" } },
    { selector: "edge.evidence-mode.device-link", style: { opacity: 0.68, "line-style": "dotted" } },
    {
      selector: "edge.evidence-mode.verified-negative",
      style: { opacity: 0.62, "line-color": T.tone.verified, "target-arrow-color": T.tone.verified },
    },

    // ---------------------------------------------------------------
    // Focus + context (§12)
    // ---------------------------------------------------------------
    // Không xoá phần không liên quan — làm mờ. Analyst vẫn cần thấy thực thể
    // đang xem nằm ở đâu trong mạng lưới.
    { selector: ".dimmed", style: { opacity: 0.12 } },
    { selector: "node.dimmed", style: { label: "" } },
    { selector: ".neighbour", style: { opacity: 0.9 } },
    { selector: ".second-hop", style: { opacity: 0.45 } },
  ];
}
