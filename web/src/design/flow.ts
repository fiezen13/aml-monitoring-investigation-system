/**
 * Hệ chuyển động của dòng tiền trên bản đồ.
 *
 * Tách khỏi `motion.ts` vì đây là một lớp khác hẳn: `motion.ts` mô tả chuyển
 * động của giao diện (panel, tab, inspector) và chạy trên React; còn ở đây là
 * chuyển động của **dữ liệu**, chạy trên GPU, cho hàng trăm hành lang cùng lúc.
 * Không có React trong đường này.
 *
 * Nguyên tắc đọc hình: mỗi hành lang gồm hai lớp.
 *
 *   đường nền   — luôn có, rất mờ, nói "tồn tại một hành lang ở đây"
 *   vệt chảy    — một đoạn sáng chạy từ nguồn tới đích, nói "tiền đang đi
 *                 hướng này, mạnh chừng này, rủi ro chừng này"
 *
 *       ───────░▒▓████▶────────────
 *
 * Ba biến, ba nghĩa, không chồng lấn:
 *
 *   bề rộng  → khối lượng giao dịch
 *   màu      → mức rủi ro (lấy nguyên từ `design/risk`)
 *   tốc độ   → mật độ giao dịch
 *
 * Không dùng một biến để nói ba điều, và không bịa ra ngữ nghĩa mà dữ liệu
 * không có.
 */

/**
 * Hằng số thị giác của dòng chảy.
 *
 * Cả bộ dựng MapLibre lẫn bộ dựng Cesium đọc từ đây. Đặt cùng một con số ở hai
 * nơi là cách chắc chắn nhất để 2D và 3D trôi khỏi nhau sau vài lần chỉnh.
 */
export const flowMotion = {
  /** Vòng chạy mỗi giây. 0,05 nghĩa là gói mất 20 giây để đi hết hành lang. */
  minSpeed: 0.045,
  maxSpeed: 0.16,

  /** Chiều dài vệt, tính theo tỷ lệ của cả hành lang. */
  normalTrailLength: 0.22,
  selectedTrailLength: 0.3,

  /** Độ mờ của đường nền — đủ để đọc topology, không đủ để cạnh tranh với vệt. */
  baseOpacity: 0.22,
  baseOpacitySuspicious: 0.3,
  baseOpacityCritical: 0.38,
  /** Hành lang không liên quan khi đang chọn một hành lang khác. */
  inactiveOpacity: 0.08,

  /** Độ sáng cực đại của vệt, cộng thêm lên trên nền. */
  trailOpacity: 0.72,
  selectedTrailOpacity: 0.95,

  /** Bề rộng tính bằng pixel màn hình. */
  minWidth: 1.2,
  maxWidth: 4.2,
  selectedWidthBonus: 1.6,
  hoverWidthBonus: 0.8,

  /**
   * Phần đầu nóng của vệt, tỷ lệ trong chiều dài vệt.
   *
   * Giữ nhỏ có chủ đích: lõi càng dài thì vệt càng giống một nét gạch trắng
   * chạy trên đường, và mất luôn cảm giác "gói dữ liệu" mà cả hiệu ứng này tồn
   * tại để tạo ra.
   */
  coreRatio: 0.1,

  /** Chuyển trạng thái hover/selected, giây. Khớp lớp L1 của `motion.ts`. */
  transitionDuration: 0.14,

  /**
   * Mức chi tiết theo tầm nhìn. Ở mức toàn cầu có tới hàng trăm hành lang chồng
   * nhau, nên vệt phải mảnh và ngắn lại; càng zoom gần càng trả về đủ chi tiết.
   */
  lod: {
    farZoom: 1.5,
    nearZoom: 5,
    farWidthScale: 0.72,
    farTrailScale: 0.72,
    farOpacityScale: 0.82,
  },
} as const;

/**
 * Neo chuẩn hoá.
 *
 * Thang tuyệt đối chứ không phải min/max của tập đang hiển thị: nếu chuẩn hoá
 * theo tập hiện tại thì cùng một hành lang sẽ đổi bề rộng mỗi khi người dùng
 * bấm Top 10 / Top 25, và bề rộng mất nghĩa.
 */
export const flowScale = {
  /** Khối lượng, USD. Dưới cận dưới là mảnh nhất, trên cận trên là dày nhất. */
  volumeMinUsd: 1e6,
  volumeMaxUsd: 1e11,
  /** Số giao dịch trong cửa sổ. */
  txnMin: 1,
  txnMax: 20_000,
} as const;

/**
 * Mô tả chuyển động của một hành lang, độc lập với engine dựng hình.
 *
 * Đây là hợp đồng duy nhất giữa nghiệp vụ và hai bộ dựng hình:
 *
 *     RouteDescriptor  →  FlowAnimationSpec  →  MapLibre | Cesium
 *
 * Không bộ dựng hình nào được tự suy ra màu, tốc độ hay bề rộng từ dữ liệu thô.
 */
export interface FlowAnimationSpec {
  id: string;
  /** Vòng mỗi giây. */
  speed: number;
  /** Lệch pha ban đầu, 0–1. Tất định theo id hành lang. */
  phase: number;
  /** Chiều dài vệt theo tỷ lệ hành lang, 0–1. */
  trailLength: number;
  baseOpacity: number;
  trailOpacity: number;
  /** Bề rộng, pixel màn hình. */
  width: number;
  /** Màu đặc của hành lang, đã qua thang rủi ro. */
  color: string;
  selected: boolean;
  /** Có hành lang khác đang được chọn — hành lang này phải lùi lại. */
  dimmed: boolean;
  /** Nét đứt cho hành lang bình thường, giữ đúng chú giải đang có. */
  dashed: boolean;
}
