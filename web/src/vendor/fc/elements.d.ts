// Khai báo custom element của prototype cho TypeScript/JSX.
//
// `charts.js` đăng ký `<fc-chart>` khi được import. React 18 không biết gì về
// custom element: nó chuyển mọi prop lạ thành attribute HTML. Engine lại đọc dữ
// liệu qua *property*, nên ở đây chỉ khai báo phần JSX cần thiết — dữ liệu do
// wrapper trong `components/fc/` gán bằng ref.

import type { DetailedHTMLProps, HTMLAttributes } from "react";

type FCElement = DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement>;

declare global {
  namespace JSX {
    interface IntrinsicElements {
      "fc-chart": FCElement;
    }
  }
}

export {};
