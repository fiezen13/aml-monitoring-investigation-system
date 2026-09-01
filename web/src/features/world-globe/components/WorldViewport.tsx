import { motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { MapData } from "../../../components/fc/WorldMap";
import { duration, easing } from "../../../design/tokens";
import { useReduced } from "../../../design/motion";
import { CesiumGlobe } from "./CesiumGlobe";
import { MapLibre2D } from "./MapLibre2D";
import { INITIAL_CAMERA, type WorldCamera, type WorldMode, type WorldRendererHandle } from "../state/worldView";

/**
 * Khung nhìn thế giới — hai bộ dựng hình, một thế giới.
 *
 * Bản trước đổi chế độ bằng `mode === "globe" ? <CesiumGlobe/> : <MapLibre2D/>`.
 * Một dòng, và nó khiến mỗi lần bấm 2D/3D là một lần: huỷ context WebGL, dựng
 * lại context mới, mất vị trí camera, quay về khung nhìn toàn cầu mặc định, và
 * chớp một khung đen ở giữa. Người dùng không cảm thấy mình vừa đổi phép chiếu
 * của cùng một thế giới — họ cảm thấy vừa mở một ứng dụng khác.
 *
 * Ở đây cả hai bộ dựng hình cùng nằm trong cây, chồng lên nhau, và việc chuyển
 * cảnh diễn ra theo trình tự:
 *
 *   1. đọc khung nhìn của bộ đang hiển thị
 *   2. dựng bộ kia nếu chưa có (Cesium chỉ khởi tạo ở lần đầu thực sự cần)
 *   3. đặt camera của nó vào đúng ngữ cảnh địa lý ấy, chưa hiện ra
 *   4. mờ chồng hai lớp trong 0,55s — lớp đi ra lùi lại 0,5% để có chiều sâu
 *   5. tắt vòng lặp dựng hình của lớp không còn hiển thị
 *
 * Lớp phủ giao diện (bộ lọc, inspector, HUD, thanh thời gian) KHÔNG nằm trong
 * component này. Chúng thuộc về `WorldPage` và không bao giờ bị tháo — đó là
 * nửa còn lại của yêu cầu "đổi phép chiếu, không đổi ứng dụng".
 */

interface Props {
  data: MapData | null;
  mode: WorldMode;
  layers: Record<string, boolean>;
  sev: string;
  typ: string;
  topN: number;
  hideNormal: boolean;
  selectedFlow: string | null;
  selectedHub: string | null;
  onPickFlow: (id: string | null) => void;
  onPickHub: (id: string | null) => void;
}

export function WorldViewport({ data, mode, ...shared }: Props) {
  const reduced = useReduced();
  const map2d = useRef<WorldRendererHandle>(null);
  const globe3d = useRef<WorldRendererHandle>(null);

  /**
   * Quả cầu chỉ được dựng khi lần đầu thực sự cần tới.
   *
   * Cesium kéo theo một context WebGL, bộ ảnh bề mặt và một vòng lặp dựng hình
   * riêng. Phần lớn phiên làm việc của chuyên viên diễn ra hoàn toàn ở bản đồ
   * 2D, nên trả giá đó ngay lúc mở trang là trả cho thứ không ai dùng. Sau khi
   * đã dựng thì giữ lại — huỷ đi nghĩa là quay về đúng vấn đề ban đầu.
   */
  const [globeMounted, setGlobeMounted] = useState(mode === "globe");
  const [globeReady, setGlobeReady] = useState(false);

  /** Khung nhìn bàn giao giữa hai bộ dựng hình tại thời điểm chuyển. */
  const handoffRef = useRef<WorldCamera>(INITIAL_CAMERA);

  const showGlobe = mode === "globe";

  // Bàn giao khung nhìn. Chạy ngay khi `mode` đổi, tức là trước khi lớp mờ chồng
  // chạy xong — bộ dựng hình sắp hiện ra phải đã ở đúng chỗ ngay từ khung hình
  // đầu tiên nó xuất hiện.
  useEffect(() => {
    const from = showGlobe ? map2d.current : globe3d.current;
    const to = showGlobe ? globe3d.current : map2d.current;
    const camera = from?.getCamera();
    if (camera) handoffRef.current = camera;

    if (showGlobe && !globeMounted) {
      // Chưa có quả cầu: `handoffRef` sẽ được truyền xuống làm khung nhìn khởi
      // tạo, xem `initialCamera` bên dưới.
      setGlobeMounted(true);
      return;
    }
    if (camera) to?.setCamera(camera);
  }, [showGlobe, globeMounted]);

  // Bộ dựng hình đã lùi về sau không được tiếp tục chiếm GPU. Chờ hết thời gian
  // chuyển cảnh rồi mới tắt: tắt ngay sẽ đóng băng đúng lớp đang mờ dần.
  useEffect(() => {
    const active = showGlobe ? globe3d.current : map2d.current;
    const idle = showGlobe ? map2d.current : globe3d.current;
    active?.setActive(true);

    const timer = window.setTimeout(
      () => idle?.setActive(false),
      reduced ? 0 : duration.spatial * 1000,
    );
    return () => window.clearTimeout(timer);
  }, [showGlobe, globeReady, reduced]);

  const onGlobeReady = useCallback(() => setGlobeReady(true), []);

  const spatial = reduced
    ? { duration: 0.01 }
    : { duration: duration.spatial, ease: easing.standard as unknown as [number, number, number, number] };

  return (
    <div className="absolute inset-0 overflow-hidden">
      <motion.div
        className="absolute inset-0"
        // Lớp lùi về sau co lại 0,5% chứ không đứng yên: một chút thị sai là đủ
        // để mắt đọc ra "cùng một cảnh, đang chuyển", thay vì hai ảnh chồng nhau.
        animate={{ opacity: showGlobe ? 0 : 1, scale: showGlobe ? 0.995 : 1 }}
        initial={false}
        transition={spatial}
        style={{ pointerEvents: showGlobe ? "none" : "auto" }}
        aria-hidden={showGlobe}
      >
        <MapLibre2D ref={map2d} data={data} initialCamera={handoffRef.current} {...shared} />
      </motion.div>

      {globeMounted && (
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: showGlobe ? 1 : 0, scale: showGlobe ? 1 : 0.995 }}
          initial={{ opacity: 0 }}
          transition={spatial}
          style={{ pointerEvents: showGlobe ? "auto" : "none" }}
          aria-hidden={!showGlobe}
        >
          <CesiumGlobe
            ref={globe3d}
            data={data}
            initialCamera={handoffRef.current}
            onReady={onGlobeReady}
            {...shared}
          />
        </motion.div>
      )}
    </div>
  );
}
