/**
 * Trạng thái khung nhìn thế giới, tách khỏi cả hai bộ dựng hình.
 *
 * Đây là điều kiện để 2D và 3D là hai phép chiếu của **một** thế giới chứ không
 * phải hai ứng dụng: không bộ dựng hình nào được giữ riêng thứ gì mà bộ kia cần
 * biết. Trước đây `WorldMap` đổi chế độ bằng cách tháo hẳn component này và dựng
 * component kia, nên vị trí camera, thực thể đang chọn và cả ngữ cảnh địa lý đều
 * biến mất sau mỗi lần bấm.
 *
 * File này không import MapLibre lẫn Cesium — nó chỉ mô tả khung nhìn và quy đổi
 * giữa hai cách đo của chúng, nên kiểm thử được mà không cần WebGL.
 */

export type WorldMode = "map" | "globe";

/** Khung nhìn ở dạng trung lập, không thuộc về engine nào. */
export interface WorldCamera {
  longitude: number;
  latitude: number;
  /**
   * Mức phóng theo thang của MapLibre (0 = cả thế giới). Chọn thang này làm
   * chuẩn vì nó rời rạc, có giới hạn rõ và dễ đọc khi gỡ lỗi hơn "độ cao camera
   * tính bằng mét".
   */
  zoom: number;
}

/** Khung nhìn mở đầu: châu Âu và châu Phi ở giữa, châu Á phải, Bắc Mỹ trái. */
export const INITIAL_CAMERA: WorldCamera = { longitude: 20, latitude: 18, zoom: 1.1 };

/** Độ phân giải Mercator tại xích đạo ở mức phóng 0, mét trên mỗi pixel. */
const EQUATOR_METERS_PER_PIXEL = 156_543.03392804097;

/** Trường nhìn dọc mặc định của Cesium (60°). */
const CESIUM_FOV = Math.PI / 3;

/** Giới hạn zoom của quả cầu — khớp `screenSpaceCameraController` trong scene.ts. */
export const GLOBE_MIN_HEIGHT = 800_000;
export const GLOBE_MAX_HEIGHT = 50_000_000;

/**
 * Trần độ cao khi bàn giao khung nhìn từ bản đồ 2D sang quả cầu.
 *
 * Thấp hơn hẳn `GLOBE_MAX_HEIGHT` vì phép quy đổi tuyến tính hết ý nghĩa ở mức
 * toàn cầu: Mercator ở mức phóng nhỏ nhất trải cả 40.000 km chu vi Trái Đất ra
 * mặt phẳng, còn trên hình cầu thì không góc nhìn nào thấy quá một nửa. Quy đổi
 * thẳng ra khoảng 39.000 km — đúng về số học, và cho ra một quả cầu bé xíu giữa
 * nền sao. 18.500 km là độ cao mà quả cầu chiếm khoảng 70% chiều cao khung, tức
 * đúng khung nhìn mở đầu mà `scene.ts` dùng.
 *
 * Ở các mức phóng gần hơn — vùng, quốc gia, thành phố — phép quy đổi vẫn chạy
 * nguyên vẹn, và đó chính là chỗ tính liên tục thực sự có giá trị: chuyên viên
 * đang xem một hành lang cụ thể thì phải thấy đúng hành lang ấy sau khi đổi
 * phép chiếu.
 */
const HANDOFF_MAX_HEIGHT = 18_500_000;

function metersPerPixel(zoom: number, latitude: number): number {
  return (EQUATOR_METERS_PER_PIXEL * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

/**
 * Mức phóng MapLibre → độ cao camera Cesium.
 *
 * Phép quy đổi cố ý xấp xỉ: Mercator và phối cảnh cầu không có ánh xạ một-một,
 * và mục tiêu ở đây không phải khớp từng pixel mà là camera 3D nhìn thấy đúng
 * vùng đất mà người dùng đang xem ở 2D. Sai vài phần trăm không ai nhận ra;
 * hạ cánh xuống nhầm châu lục thì có.
 */
export function zoomToHeight(zoom: number, latitude: number, viewportHeightPx: number): number {
  const groundHeightMeters = metersPerPixel(zoom, latitude) * viewportHeightPx;
  const height = groundHeightMeters / (2 * Math.tan(CESIUM_FOV / 2));
  return Math.min(HANDOFF_MAX_HEIGHT, Math.max(GLOBE_MIN_HEIGHT, height));
}

/** Độ cao camera Cesium → mức phóng MapLibre. Nghịch đảo của `zoomToHeight`. */
export function heightToZoom(height: number, latitude: number, viewportHeightPx: number): number {
  const groundHeightMeters = height * 2 * Math.tan(CESIUM_FOV / 2);
  const perPixel = groundHeightMeters / Math.max(1, viewportHeightPx);
  const zoom = Math.log2((EQUATOR_METERS_PER_PIXEL * Math.cos((latitude * Math.PI) / 180)) / perPixel);
  return Math.min(18, Math.max(0, zoom));
}

/**
 * Giao diện mệnh lệnh mà mỗi bộ dựng hình phải cung cấp.
 *
 * Camera là trạng thái mệnh lệnh sống trong WebGL — không có state React nào mô
 * tả được "hãy đang ở chỗ này". Vì vậy khung nhìn được đọc/ghi qua ref tại đúng
 * thời điểm chuyển chế độ, thay vì đồng bộ ngược lên React ở mỗi khung hình
 * (việc đó sẽ dựng lại cây component 60 lần mỗi giây trong lúc người dùng kéo
 * bản đồ).
 */
export interface WorldRendererHandle {
  /** Khung nhìn hiện tại, hoặc null nếu bộ dựng hình chưa sẵn sàng. */
  getCamera(): WorldCamera | null;
  /** Đặt khung nhìn ngay lập tức, không animation. */
  setCamera(camera: WorldCamera): void;
  /**
   * Bật/tắt vòng lặp dựng hình. Bộ dựng hình không hiển thị phải ngừng chiếm
   * GPU — hai engine WebGL cùng vẽ liên tục là cách chắc chắn để rớt khung hình
   * trên máy tính xách tay của chuyên viên tuân thủ.
   */
  setActive(active: boolean): void;
}
