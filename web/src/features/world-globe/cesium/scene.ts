/**
 * Dựng và cấu hình Cesium Viewer cho bản đồ giám sát AML.
 *
 * Cesium ở đây là bộ dựng hình, không phải vỏ ứng dụng: mọi widget mặc định đều
 * tắt, còn thanh điều khiển, chú giải và bảng chi tiết vẫn do React sở hữu.
 */

import {
  Cartesian3,
  Color,
  Ion,
  Math as CesiumMath,
  SceneMode,
  TileMapServiceImageryProvider,
  Viewer,
  buildModuleUrl,
  createWorldImageryAsync,
} from "cesium";

import "cesium/Build/Cesium/Widgets/widgets.css";

import { atmosphere, imageryTone, mapSurface } from "../../../design/adapters/mapTheme";

/** Độ cao camera cho khung nhìn toàn cầu ban đầu, tính bằng mét. */
// 18.500 km cho quả cầu chiếm khoảng 70% chiều cao khung bản đồ — đủ để đọc
// là hình cầu mà vẫn còn khoảng trống quanh rìa.
const GLOBAL_VIEW_HEIGHT = 18_500_000;

/**
 * Kinh độ trung tâm khung nhìn mở đầu. 20°Đ đặt châu Âu và châu Phi vào giữa,
 * châu Á ở rìa phải và Bắc Mỹ ở rìa trái — đúng yêu cầu "thấy cả bốn khu vực".
 */
const OPENING_LONGITUDE = 20;
const OPENING_LATITUDE = 18;

/** Giới hạn zoom: đủ gần để đọc hành lang, đủ xa để không chui vào trong cầu. */
const MIN_ZOOM_METERS = 800_000;
const MAX_ZOOM_METERS = 50_000_000;

export type ImagerySource = "ion" | "offline";

export interface SceneHandle {
  viewer: Viewer;
  imagery: ImagerySource;
}

/**
 * Ảnh bề mặt dự phòng đi kèm gói `cesium`, không cần mạng.
 *
 * Console tuân thủ ngân hàng thường nằm sau mạng chặn Internet ra ngoài, mà
 * Cesium World Imagery lại là dịch vụ trực tuyến — mỗi ô ảnh là một request tới
 * assets.ion.cesium.com. Natural Earth II độ phân giải thấp nhưng nằm sẵn trong
 * bundle, nên quả cầu vẫn là Trái Đất thật khi không có mạng hoặc không có token.
 */
function offlineImagery(): Promise<TileMapServiceImageryProvider> {
  return TileMapServiceImageryProvider.fromUrl(buildModuleUrl("Assets/Textures/NaturalEarthII"));
}

/**
 * Hạ sáng và giảm bão hoà ảnh nền.
 *
 * Bảng điều khiển này là nền tối, và tín hiệu AML mới là thứ cần nổi bật. Ảnh vệ
 * tinh nguyên bản sáng và rực màu tới mức cung giao dịch chìm nghỉm.
 */
function applyDarkTone(viewer: Viewer): void {
  const layer = viewer.imageryLayers.get(0);
  if (!layer) return;
  layer.brightness = imageryTone.brightness;
  layer.saturation = imageryTone.saturation;
  layer.contrast = imageryTone.contrast;
  layer.gamma = imageryTone.gamma;
}

async function attachImagery(viewer: Viewer, token: string | undefined): Promise<ImagerySource> {
  if (token) {
    Ion.defaultAccessToken = token;
    try {
      viewer.imageryLayers.removeAll();
      viewer.imageryLayers.addImageryProvider(await createWorldImageryAsync());
      return "ion";
    } catch (error) {
      // Hỏng token, hết hạn, hoặc bị chặn mạng — không được để cả bảng điều khiển
      // chết theo. Rơi về ảnh ngoại tuyến và báo cho lập trình viên.
      console.error("[globe] không dùng được Cesium World Imagery, chuyển sang ảnh ngoại tuyến:", error);
    }
  }
  viewer.imageryLayers.removeAll();
  viewer.imageryLayers.addImageryProvider(await offlineImagery());
  return "offline";
}

export async function createScene(container: HTMLElement, token?: string): Promise<SceneHandle> {
  const viewer = new Viewer(container, {
    // Ứng dụng AML đã sở hữu toàn bộ giao diện; Cesium chỉ dựng hình.
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    homeButton: false,
    geocoder: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    selectionIndicator: false,
    infoBox: false,
    // Bảng chi tiết là component React; để Cesium tự chọn thực thể sẽ sinh ra
    // hai nguồn sự thật cho cùng một trạng thái.
    scene3DOnly: false,
    // Tắt hộp thoại lỗi của Cesium. Khi không có WebGL — GPU nằm trong danh
    // sách chặn, phiên remote desktop, máy ảo không tăng tốc phần cứng — nó tự
    // chèn một hộp nền trắng chữ tiếng Anh vào giữa bảng điều khiển tối. Lỗi ấy
    // đã có đường xử lý riêng ở CesiumGlobe với đúng tông màu và đúng tiếng
    // Việt; hai thông báo cho cùng một sự cố thì một cái là thừa.
    showRenderLoopErrors: false,
    // Ảnh nền do attachImagery() gắn, để tránh Viewer tự gọi ion khi khởi tạo.
    baseLayer: false,
  });

  const imagery = await attachImagery(viewer, token);
  applyDarkTone(viewer);

  const { scene } = viewer;
  scene.backgroundColor = Color.fromCssColorString(mapSurface.space);
  if (scene.skyAtmosphere) {
    scene.skyAtmosphere.show = true;
    // Kéo bầu khí quyển về đúng tông lạnh của bản đồ 2D. Mặc định của Cesium là
    // một vành xanh dương sáng — đẹp trong ứng dụng địa cầu, nhưng ở đây nó là
    // vật thể sáng nhất màn hình và hút mắt khỏi hành lang giao dịch.
    scene.skyAtmosphere.hueShift = atmosphere.hueShift;
    scene.skyAtmosphere.saturationShift = atmosphere.saturationShift;
    scene.skyAtmosphere.brightnessShift = atmosphere.brightnessShift;
  }
  scene.globe.showGroundAtmosphere = true;
  scene.globe.baseColor = Color.fromCssColorString(mapSurface.globeBase);
  // Tắt chiếu sáng theo mặt trời: nửa quả cầu chìm trong đêm là không dùng được
  // cho một màn hình giám sát trực ban 24/7.
  scene.globe.enableLighting = false;
  scene.fog.enabled = true;
  scene.highDynamicRange = false;

  const controller = scene.screenSpaceCameraController;
  controller.minimumZoomDistance = MIN_ZOOM_METERS;
  controller.maximumZoomDistance = MAX_ZOOM_METERS;
  controller.enableCollisionDetection = true;

  viewer.camera.setView({
    destination: Cartesian3.fromDegrees(OPENING_LONGITUDE, OPENING_LATITUDE, GLOBAL_VIEW_HEIGHT),
    orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
  });

  return { viewer, imagery };
}

/** Đưa camera về khung nhìn toàn cầu mở đầu. */
export function resetCamera(viewer: Viewer, durationSeconds = 0.8): void {
  viewer.camera.flyTo({
    destination: Cartesian3.fromDegrees(OPENING_LONGITUDE, OPENING_LATITUDE, GLOBAL_VIEW_HEIGHT),
    orientation: { heading: 0, pitch: CesiumMath.toRadians(-90), roll: 0 },
    duration: durationSeconds,
  });
}

/**
 * Chuyển giữa 2D và 3D bằng chính cơ chế của Cesium.
 *
 * Không huỷ rồi dựng lại Viewer: làm vậy mất thực thể đang chọn, mất vị trí
 * camera, và rò rỉ một context WebGL mỗi lần bấm.
 */
export function morphTo(viewer: Viewer, mode: "map" | "globe", seconds = 0.8): void {
  const target = mode === "globe" ? SceneMode.SCENE3D : SceneMode.SCENE2D;
  if (viewer.scene.mode === target) return;
  if (mode === "globe") viewer.scene.morphTo3D(seconds);
  else viewer.scene.morphTo2D(seconds);
}
