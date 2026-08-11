// Khai báo custom element của prototype cho TypeScript/JSX.
//
// Năm engine trong thư mục này đăng ký custom element khi được import. React
// 18 không biết gì về chúng: nó chuyển mọi prop lạ thành attribute HTML. Các
// engine lại đọc dữ liệu qua *property*, nên ở đây chỉ khai báo `ref` và các
// attribute tĩnh — dữ liệu do wrapper trong `components/fc/` gán bằng ref.

import type { DetailedHTMLProps, HTMLAttributes } from "react";

type FCElement = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement>;

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "fc-chart": FCElement;
      "fc-chart-card": FCElement & {
        title?: string;
        subtitle?: string;
        height?: string;
        note?: string;
        tools?: string;
      };
      "fc-worldmap": FCElement;
      "fc-graph": FCElement;
      "fc-globe3d": FCElement;
    }
  }
}

export {};
