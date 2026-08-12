import { InvestigationGraph } from "../features/network-graph";

/**
 * Network Graph — đồ thị thực thể của toàn bộ mạng lưới mô phỏng.
 *
 * Khác với `NetworkPage` (đồ thị gọn theo một vụ việc, dựng bằng React Flow),
 * màn hình này vẽ toàn bộ mạng lưới bằng engine canvas riêng vì số đỉnh lớn hơn
 * nhiều và cần gom cụm, phân tầng, lọc theo thời gian.
 *
 * Toàn bộ phần thân nằm trong `features/network-graph` — trang chỉ còn là điểm
 * gắn vào router.
 */
export function EntityNetworkPage() {
  return <InvestigationGraph />;
}
