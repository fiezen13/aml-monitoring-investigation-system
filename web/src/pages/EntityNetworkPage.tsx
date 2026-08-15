import { InvestigationGraph } from "../features/network-graph";

/**
 * Network Graph — đồ thị thực thể của release đang hoạt động.
 *
 * Khác với `NetworkPage` (đồ thị gọn theo một vụ việc, dựng bằng React Flow),
 * màn hình này tải tập ứng viên bằng engine canvas riêng, sau đó tách connected
 * component và chỉ vẽ một mạng độc lập tại một thời điểm.
 *
 * Toàn bộ phần thân nằm trong `features/network-graph` — trang chỉ còn là điểm
 * gắn vào router.
 */
export function EntityNetworkPage() {
  return <InvestigationGraph />;
}
