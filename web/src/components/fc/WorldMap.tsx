import { useEffect, useRef } from "react";

import "../../vendor/fc/worldmap.js";
import "../../vendor/fc/globe3d.js";

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

/** Phủ kín khung cha. Xem ghi chú ở cuối file về việc không dùng className. */
const FILL = { position: "absolute", inset: 0 } as const;

interface Props {
  data: MapData | null;
  mode: "map" | "globe";
  layers: Record<string, boolean>;
  sev: string;
  typ: string;
  topN: number;
  hideNormal: boolean;
  paused: boolean;
  speed: number;
  replay: { on: boolean; t: number };
  selectedFlow: string | null;
  selectedHub: string | null;
  onPickFlow: (id: string | null) => void;
  onPickHub: (id: string | null) => void;
}

/**
 * Bản đồ dòng tiền toàn cầu — 2D hoặc quả cầu 3D, cùng một bộ dữ liệu.
 *
 * Cả hai engine nhận trạng thái qua property setter (mỗi setter tự vẽ lại khi
 * giá trị đổi), nên ở đây chỉ đồng bộ props xuống element sau mỗi lần render.
 */
export function WorldMap({
  data,
  mode,
  layers,
  sev,
  typ,
  topN,
  hideNormal,
  paused,
  speed,
  replay,
  selectedFlow,
  selectedHub,
  onPickFlow,
  onPickHub,
}: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current as (HTMLElement & Record<string, unknown>) | null;
    if (!el || !data) return;
    el.data = data;
    el.layers = layers;
    el.sev = sev;
    el.typ = typ;
    el.topN = topN;
    el.hideNormal = hideNormal;
    el.paused = paused;
    el.speed = speed;
    el.replay = replay;
    el.selection = selectedFlow;
    el.hubSelection = selectedHub;
  }, [data, layers, sev, typ, topN, hideNormal, paused, speed, replay, selectedFlow, selectedHub, mode]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    // Cả `fc-worldmap` và `fc-globe3d` phát cùng bộ sự kiện này, nên đổi 2D ↔ 3D
    // không cần thay đổi phía React.
    const onFlow = (e: Event) => {
      onPickFlow(((e as CustomEvent).detail?.id as string) ?? null);
      onPickHub(null);
    };
    const onHub = (e: Event) => {
      onPickHub(((e as CustomEvent).detail?.id as string) ?? null);
      onPickFlow(null);
    };
    const onClear = () => {
      onPickFlow(null);
      onPickHub(null);
    };
    el.addEventListener("flowselect", onFlow);
    el.addEventListener("hubselect", onHub);
    el.addEventListener("clearselect", onClear);
    return () => {
      el.removeEventListener("flowselect", onFlow);
      el.removeEventListener("hubselect", onHub);
      el.removeEventListener("clearselect", onClear);
    };
  }, [onPickFlow, onPickHub, mode]);

  // `key` theo mode buộc React huỷ element cũ và tạo mới khi đổi 2D ↔ 3D —
  // hai engine giữ trạng thái camera riêng, tái dùng node sẽ lẫn trạng thái.
  //
  // Định vị bằng `style` chứ không bằng `className`: với custom element, React
  // 18 đặt prop `className` thành một attribute tên `classname`, và CSS không
  // nhìn thấy nó — element sẽ có chiều cao 0 và canvas không vẽ được gì.
  return mode === "globe" ? (
    <fc-globe3d key="globe" ref={ref} style={FILL} />
  ) : (
    <fc-worldmap key="map" ref={ref} style={FILL} />
  );
}
