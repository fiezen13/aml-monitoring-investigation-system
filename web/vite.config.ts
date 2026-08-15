import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import cesium from "vite-plugin-cesium";

// Khi chạy `npm run dev` ngoài Docker, proxy về API ở localhost:8000.
// Trong Docker, nginx đảm nhiệm việc này (xem web/nginx.conf).
export default defineConfig({
  // `cesium()` sao chép Workers/Assets/ThirdParty/Widgets của Cesium vào thư mục
  // build và đặt CESIUM_BASE_URL. Cesium nạp mấy thứ đó lúc chạy bằng đường dẫn
  // tương đối, nên không có bước này thì viewer dựng lên rồi chết khi đi tìm
  // worker giải mã ảnh.
  plugins: [react(), cesium()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
      "/grafana": {
        target: process.env.VITE_GRAFANA_TARGET ?? "http://localhost:3000",
        changeOrigin: true,
        headers: { "X-WEBAUTH-USER": "fin07-console", "X-WEBAUTH-ROLE": "Viewer" },
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Cesium là bundle khổng lồ đòi WebGL; test dùng mock ở src/test/cesiumMock.ts.
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
