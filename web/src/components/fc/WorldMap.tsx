import { CesiumGlobe } from "../../features/world-globe/components/CesiumGlobe";
import { MapLibre2D } from "../../features/world-globe/components/MapLibre2D";

export interface MapHub {
  id: string;
  name: string;
  lat: number;
  lon: number;
  size: number;
  vol: string;
  entities: number;
  alerts: number;
  inb?: number;
  outb?: number;
  cases?: number;
  riskN?: number;
}

export interface MapFlow {
  id: string;
  sn: string;
  tn: string;
  slat: number;
  slon: number;
  tlat: number;
  tlon: number;
  /** Kênh: bank | p2p | vasp | chain | gamb | proj */
  ch: string;
  /** Mức độ: ok | warn | crit */
  risk: string;
  vol: string;
  txn: number;
  typ: string | null;
  riskN?: number;
  cur?: string;
  t0?: number;
  ph?: number;
  firstSeen?: string;
  lastSeen?: string;
  alertN?: number;
  cases?: string[];
  status?: string;
}

export interface MapData {
  hubs: MapHub[];
  flows: MapFlow[];
}

interface Props {
  data: MapData | null;
  mode: "map" | "globe";
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

/**
 * Bản đồ dòng tiền toàn cầu — 2D hoặc quả cầu 3D, cùng một bộ dữ liệu.
 *
 * Lớp mỏng giữ nguyên hợp đồng props cũ để WorldPage không phải đổi, còn phần
 * dựng hình do Cesium đảm nhiệm.
 */
export function WorldMap({
  data,
  mode,
  layers,
  sev,
  typ,
  topN,
  hideNormal,
  selectedFlow,
  selectedHub,
  onPickFlow,
  onPickHub,
}: Props) {
  // Hai renderer, một bộ dữ liệu và một bộ state. 3D là Cesium cho nhận thức
  // toàn cảnh; 2D là MapLibre cho điều tra — nền tối tối giản, không ảnh vệ tinh.
  // Cả hai đọc cùng adapter nên luật rủi ro và luật lọc không bị nhân đôi.
  const shared = {
    data,
    layers,
    sev,
    typ,
    topN,
    hideNormal,
    selectedFlow,
    selectedHub,
    onPickFlow,
    onPickHub,
  };
  return mode === "globe" ? <CesiumGlobe mode="globe" {...shared} /> : <MapLibre2D {...shared} />;
}
