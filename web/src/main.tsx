import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { installCanvasTheme } from "./design/adapters/canvasTheme";
import "./styles/index.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Không tìm thấy phần tử #root");
}

// Phải chạy trước lần dựng đầu tiên: engine canvas đọc biến CSS ngay lúc module
// của nó được nạp, và nếu biến chưa có thì nó khoá vào bảng màu dự phòng.
installCanvasTheme();

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
