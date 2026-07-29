import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Khi chạy `npm run dev` ngoài Docker, proxy về API ở localhost:8000.
// Trong Docker, nginx đảm nhiệm việc này (xem web/nginx.conf).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
