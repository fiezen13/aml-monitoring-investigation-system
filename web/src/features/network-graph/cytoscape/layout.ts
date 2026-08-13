import type { LayoutOptions } from "cytoscape";

import type { LayoutKey } from "../types/graph.types";

/**
 * Cấu hình layout.
 *
 * fCoSE là lựa chọn mặc định cho khám phá mạng lưới: nó xử lý được compound
 * node (cụm đang mở) và cho ra bố cục ổn định giữa các lần chạy, hai thứ mà bộ
 * layout tự viết trước đây không có.
 *
 * Layout KHÔNG chạy liên tục. Nó chạy đúng bốn thời điểm — dựng đồ thị, mở
 * cụm, mở rộng lân cận, người dùng bấm sắp xếp lại (§23). Chạy lại ở mỗi lần
 * hover hay chọn thì mỗi thao tác của analyst lại làm cả mạng lưới nhảy chỗ, và
 * họ mất luôn bản đồ ghi nhớ trong đầu về nơi từng thực thể đứng.
 */

/** Chất lượng thấp hơn khi đồ thị lớn — chờ 3 giây để xếp đẹp là quá lâu. */
function quality(nodeCount: number): "draft" | "default" | "proof" {
  if (nodeCount > 240) return "draft";
  if (nodeCount > 90) return "default";
  return "proof";
}

export function fcoseOptions(nodeCount: number, animate: boolean): LayoutOptions {
  return {
    name: "fcose",
    quality: quality(nodeCount),
    randomize: true,
    animate,
    animationDuration: 420,
    fit: true,
    padding: 48,
    // Khoảng cách đỉnh: đủ để nhãn dưới đỉnh không đè lên đỉnh bên cạnh. Đây
    // là nguyên nhân trực tiếp của "nhiều node gần nhau bị chồng chữ".
    nodeSeparation: 130,
    idealEdgeLength: () => 140,
    edgeElasticity: () => 0.45,
    nodeRepulsion: () => 9000,
    gravity: 0.22,
    gravityRange: 3.2,
    // Cụm đang mở là compound node; nới thêm để khung cụm không ôm sát đỉnh.
    gravityCompound: 1.1,
    gravityRangeCompound: 1.4,
    nestingFactor: 0.15,
    numIter: 2500,
    tile: true,
    tilingPaddingVertical: 24,
    tilingPaddingHorizontal: 24,
    uniformNodeDimensions: false,
  } as unknown as LayoutOptions;
}

/**
 * Layout theo chặng dòng tiền — trái sang phải, mỗi chặng một cột.
 *
 * Giữ lại vì nó trả lời một câu hỏi mà fCoSE không trả lời được: "tiền đi theo
 * thứ tự nào". fCoSE tối ưu khoảng cách, nên hai chặng liền nhau có thể nằm
 * cạnh nhau theo chiều dọc và mạch tiền biến mất.
 */
export function presetOptions(animate: boolean): LayoutOptions {
  return {
    name: "preset",
    animate,
    animationDuration: 360,
    fit: true,
    padding: 48,
  } as unknown as LayoutOptions;
}

export function layoutFor(key: LayoutKey, nodeCount: number, animate: boolean): LayoutOptions {
  // `flow` và `hierarchy` cần toạ độ do bộ layout theo chặng ghi sẵn vào node
  // data; hai chế độ còn lại giao cho fCoSE.
  if (key === "flow" || key === "hierarchy") return presetOptions(animate);
  return fcoseOptions(nodeCount, animate);
}
