/**
 * `cytoscape-fcose` không kèm khai báo kiểu và không có gói @types.
 *
 * Chỉ cần đúng một điều từ nó: một hàm nhận `cytoscape` để đăng ký extension.
 * Khai báo hẹp như vậy tốt hơn `any` — nó vẫn bắt lỗi nếu ai đó dùng sai.
 */
declare module "cytoscape-fcose" {
  import type cytoscape from "cytoscape";

  const ext: cytoscape.Ext;
  export default ext;
}
