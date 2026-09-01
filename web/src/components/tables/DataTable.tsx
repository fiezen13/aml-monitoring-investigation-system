/**
 * Lớp tương thích — bảng thật nằm ở `components/ui/DataTable`.
 *
 * Bản mới nắm luôn cả bốn trạng thái (đang tải, lỗi, rỗng, có dữ liệu) và hỗ
 * trợ sắp xếp; các trang cũ chỉ truyền dữ liệu nên chúng nhận phần hình thức
 * thống nhất mà không phải đổi gì.
 *
 * @deprecated Import `DataTable` và `Column` từ `components/ui`.
 */

export { DataTable, type Column } from "../ui/DataTable";
