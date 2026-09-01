import { WorldViewport } from "../../features/world-globe/components/WorldViewport";

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
  /**
   * Khối lượng dạng số, USD. Khác `vol` vốn đã được định dạng để hiển thị.
   * Bề rộng đường dòng tiền lấy từ đây, nên nó phải là số chứ không phải chuỗi.
   */
  volUsd?: number;
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
 * Lớp mỏng giữ hợp đồng props cũ; toàn bộ việc điều phối hai bộ dựng hình và
 * chuyển cảnh giữa chúng nằm ở `WorldViewport`. File này chỉ còn là nơi khai
 * báo hình dạng dữ liệu mà cả hai bộ dựng hình cùng đọc.
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
  return (
    <WorldViewport
      data={data}
      mode={mode}
      layers={layers}
      sev={sev}
      typ={typ}
      topN={topN}
      hideNormal={hideNormal}
      selectedFlow={selectedFlow}
      selectedHub={selectedHub}
      onPickFlow={onPickFlow}
      onPickHub={onPickHub}
    />
  );
}
