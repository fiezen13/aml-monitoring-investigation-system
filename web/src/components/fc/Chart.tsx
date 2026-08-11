import { useEffect, useRef } from "react";

import "../../vendor/fc/charts.js";

/**
 * Đặc tả biểu đồ cho `<fc-chart>`.
 *
 * Engine nhận nhiều loại spec khác nhau tuỳ `type`; các trường dưới đây là
 * hợp của tất cả. Không tách thành union vì hầu hết chỗ dùng đều dựng spec
 * động từ dữ liệu API, và union sẽ bắt phải ép kiểu ở mọi lời gọi.
 */
export interface ChartSeries {
  name: string;
  data: (number | null)[];
  color?: string;
  fill?: boolean;
  hidden?: boolean;
  unit?: string;
  /** `raw` giữ nguyên số, mặc định rút gọn thành K/M/B. */
  fmt?: "raw";
  /** Vẽ theo trục phải. */
  y2?: boolean;
  dashed?: boolean;
}

export interface ChartItem {
  label: string;
  value: number;
  color?: string;
  sub?: string;
  target?: number;
  pctOfPrev?: string;
  /** Cột giảm trong biểu đồ waterfall. */
  negative?: boolean;
  /** Dùng cho type `percentile`. */
  pct?: number;
  p50?: number;
  p95?: number;
  unit?: string;
}

export interface ChartSpec {
  type:
    | "line"
    | "area"
    | "stackarea"
    | "bars"
    | "stackbars"
    | "hbars"
    | "donut"
    | "heat"
    | "sankey"
    | "spark"
    | "waterfall"
    | "funnel"
    | "percentile";
  labels?: string[];
  series?: ChartSeries[];
  items?: ChartItem[];
  /** heat */
  rows?: string[];
  cols?: string[];
  data?: number[][];
  /** sankey */
  nodes?: { name: string; col: number; color?: string }[];
  links?: { source: number; target: number; value: number; color?: string }[];
  unit?: string;
  max?: number;
  min?: number;
  y2?: boolean;
  y2max?: number;
  hideY?: boolean;
  refs?: { v: number; label?: string; color?: string }[];
  compare?: { series: ChartSeries[] };
  /** Các biểu đồ cùng `syncGroup` sẽ đồng bộ vị trí con trỏ. */
  syncGroup?: string;
}

interface Props {
  spec: ChartSpec | null;
  height?: number | string;
  /** Nhận sự kiện click vào một điểm/cột/ô. */
  onPick?: (detail: Record<string, unknown>) => void;
  /** Nhận khoảng vừa được kéo chọn trên trục thời gian. */
  onBrush?: (detail: { from: number; to: number; labels: string[] }) => void;
}

/**
 * Bọc custom element `<fc-chart>` (canvas) cho React.
 *
 * Dữ liệu truyền qua *property* `.data` chứ không qua attribute: spec là object
 * và attribute chỉ chứa được chuỗi. Vì vậy phải gán bằng ref sau khi render.
 */
export function Chart({ spec, height, onPick, onBrush }: Props) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current as (HTMLElement & { data?: ChartSpec | null }) | null;
    if (el) el.data = spec;
  }, [spec]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const pick = (e: Event) => onPick?.((e as CustomEvent).detail);
    const brush = (e: Event) => onBrush?.((e as CustomEvent).detail);
    el.addEventListener("pick", pick);
    el.addEventListener("brush", brush);
    return () => {
      el.removeEventListener("pick", pick);
      el.removeEventListener("brush", brush);
    };
  }, [onPick, onBrush]);

  // Kích thước đặt bằng `style`, không bằng `className`: với custom element,
  // React 18 đặt prop `className` thành attribute tên `classname` mà CSS không
  // nhìn thấy — element sẽ cao 0 và canvas im lặng không vẽ gì.
  return (
    <fc-chart
      ref={ref}
      style={{ height: typeof height === "number" ? `${height}px` : height, display: "block", width: "100%" }}
    />
  );
}
