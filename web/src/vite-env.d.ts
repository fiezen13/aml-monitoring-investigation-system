/// <reference types="vite/client" />

interface ImportMetaEnv {
  /**
   * Token truy cập Cesium ion cho ảnh vệ tinh World Imagery.
   *
   * Đây là token công khai phía trình duyệt, nhưng vẫn cấu hình qua biến môi
   * trường chứ không viết thẳng vào mã nguồn. Thiếu token thì quả cầu tự dùng
   * ảnh Natural Earth II đóng gói sẵn — vẫn là Trái Đất thật, chỉ kém chi tiết.
   */
  readonly VITE_CESIUM_ION_TOKEN?: string;
  readonly VITE_API_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
