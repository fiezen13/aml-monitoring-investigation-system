import { useEffect, useRef } from "react";

import "../../vendor/fc/netgraph.js";

export interface GraphNode {
  id: string;
  /** account | person | wallet | device | platform | org | token | contract | alert | case */
  type: string;
  label: string;
  sub?: string;
  risk: number;
  /** Bán kính vẽ; bỏ trống thì engine tự suy từ bậc của đỉnh. */
  r?: number;
  /** Thời điểm xuất hiện, chuẩn hoá 0→1 để chạy thanh trượt thời gian. */
  t?: number;
  ev?: string[];
  comm?: string;
  first?: string;
  last?: string;
  /** Đánh dấu hard negative — thực thể hợp pháp cố ý đưa vào để kiểm tra. */
  negative?: boolean;
}

export interface GraphEdge {
  s: string;
  t: string;
  /** transfer | owns | device | swap | bridge | control */
  kind: string;
  label?: string;
  amt?: number;
  w?: number;
  time?: number;
  ev?: string;
  txns?: string;
  /** Cạnh do mô hình suy ra chứ không quan sát trực tiếp. */
  inferred?: boolean;
  conf?: number;
  logic?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface Props {
  data: GraphData | null;
  highlightPath?: string[] | null;
  filterEdges?: Record<string, boolean>;
  filterTypes?: Record<string, boolean>;
  minAmt?: number;
  riskMin?: number;
  /** Vị trí thanh trượt thời gian 0→1; chỉ hiện thực thể có `t` nhỏ hơn. */
  timeT?: number;
  perf?: boolean;
  onSelectNode?: (node: GraphNode | null) => void;
  onSelectEdge?: (edge: (GraphEdge & { kindName: string; sLabel: string; tLabel: string }) | null) => void;
  onExpand?: (detail: { id: string; label: string }) => void;
  /** Ghi đè cách định vị; mặc định phủ kín khung cha. */
  style?: React.CSSProperties;
}

/**
 * Phủ kín khung cha.
 *
 * Dùng `style` chứ không `className`: với custom element, React 18 đặt prop
 * `className` thành attribute tên `classname`, CSS không nhìn thấy, và element
 * sẽ có chiều cao 0 — canvas không vẽ được gì mà cũng không báo lỗi.
 */
const FILL: React.CSSProperties = { position: "absolute", inset: 0 };

/**
 * Đồ thị mạng lưới thực thể — layout lực trên canvas, gom cụm theo cộng đồng.
 *
 * Engine chạy vòng lặp mô phỏng riêng, nên chỉ đẩy props xuống và để nó tự vẽ.
 */
export function NetGraph({
  data,
  highlightPath = null,
  filterEdges,
  filterTypes,
  minAmt = 0,
  riskMin = 0,
  timeT = 1,
  perf = false,
  onSelectNode,
  onSelectEdge,
  onExpand,
  style,
}: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current as (HTMLElement & Record<string, unknown>) | null;
    if (!el || !data) return;
    el.data = data;

    // `fit()` của engine thoát ngay nếu element chưa có chiều rộng, và dữ liệu
    // thường được gán trước khi trình duyệt tính xong bố cục — khi đó đồ thị
    // vẫn chạy nhưng camera nằm ngoài vùng nhìn, mặt canvas trông như trống.
    // Thử lại vài khung hình cho tới khi element có kích thước thật.
    let tries = 0;
    let raf = 0;
    const tryFit = () => {
      if (!ref.current) return;
      if (ref.current.clientWidth > 0) {
        (ref.current as HTMLElement & { fit?: () => void }).fit?.();
        return;
      }
      if (++tries < 30) raf = requestAnimationFrame(tryFit);
    };
    raf = requestAnimationFrame(tryFit);
    return () => cancelAnimationFrame(raf);
  }, [data]);

  useEffect(() => {
    const el = ref.current as (HTMLElement & Record<string, unknown>) | null;
    if (!el) return;
    el.highlightPath = highlightPath;
    if (filterEdges) el.filterEdges = filterEdges;
    if (filterTypes) el.filterTypes = filterTypes;
    el.minAmt = minAmt;
    el.riskMin = riskMin;
    el.timeT = timeT;
    el.perf = perf;
  }, [highlightPath, filterEdges, filterTypes, minAmt, riskMin, timeT, perf]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onNode = (e: Event) => onSelectNode?.((e as CustomEvent).detail);
    const onEdge = (e: Event) => onSelectEdge?.((e as CustomEvent).detail);
    const onExp = (e: Event) => onExpand?.((e as CustomEvent).detail);
    el.addEventListener("nodeselect", onNode);
    el.addEventListener("edgeselect", onEdge);
    el.addEventListener("expand", onExp);
    return () => {
      el.removeEventListener("nodeselect", onNode);
      el.removeEventListener("edgeselect", onEdge);
      el.removeEventListener("expand", onExp);
    };
  }, [onSelectNode, onSelectEdge, onExpand]);

  return <fc-graph ref={ref} style={style ?? FILL} />;
}
