# Vendored — engine đồ hoạ của prototype "Financial City AML"

Năm file `.js` trong thư mục này được **sao chép nguyên trạng** từ
`docs/design/prototype/`. Không sửa chúng tại đây.

| File           | Custom element   | Vai trò                                                    |
| -------------- | ---------------- | ---------------------------------------------------------- |
| `charts.js`    | `<fc-chart>`     | 12 loại biểu đồ trên canvas, có tooltip/zoom/brush          |
| `chartcard.js` | `<fc-chart-card>`| Khung thẻ quanh biểu đồ: tiêu đề, nút xem dữ liệu, tải về   |
| `worldmap.js`  | `<fc-worldmap>`  | Bản đồ thế giới 2D, cung dòng tiền có hạt chuyển động       |
| `netgraph.js`  | `<fc-graph>`     | Đồ thị lực, gom cụm cộng đồng, lọc theo thời gian           |
| `globe3d.js`   | `<fc-globe3d>`   | Quả cầu 3D, cùng dữ liệu với `fc-worldmap`                  |

## Vì sao vendor thay vì viết lại

Prototype là bản thiết kế đã chốt. Viết lại engine canvas bằng thư viện khác
sẽ cho ra hình ảnh *gần giống* — và mọi khác biệt nhỏ đều là một quyết định
thiết kế bị thay đổi mà không ai duyệt. Giữ nguyên file gốc thì giao diện chạy
thật khớp đúng bản thiết kế, và khi prototype cập nhật thì chỉ cần chép đè.

## Cách dùng từ React

Các file tự đăng ký custom element khi được import (IIFE, không export gì) và
đều có bảo vệ `customElements.get(...)` nên import nhiều lần vô hại. Chúng
nhận dữ liệu qua **property**, không phải attribute — nên phải gán bằng ref
chứ không đặt trong JSX:

```tsx
const el = useRef<HTMLElement>(null);
useEffect(() => { (el.current as any).data = spec; }, [spec]);
return <fc-chart ref={el} />;
```

Các wrapper React đã làm sẵn việc này, dùng chúng thay vì gọi thẳng:
`components/fc/Chart.tsx`, `ChartCard.tsx`, `WorldMap.tsx`, `NetGraph.tsx`.

Khai báo kiểu cho JSX nằm ở `web/src/vendor/fc/elements.d.ts`.
