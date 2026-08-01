# ---- Stage 1: Build ----
FROM node:22-alpine AS builder

WORKDIR /app

# Copy manifest trước để lớp cài đặt phụ thuộc được cache riêng: sửa mã nguồn
# không làm cài lại node_modules.
COPY package.json package-lock.json ./
RUN npm ci

# postcss.config.js và tailwind.config.js phải có mặt, không phải tuỳ chọn:
# thiếu chúng thì Vite build vẫn thành công nhưng PostCSS không chạy, và CSS
# xuất ra không có một utility class nào của Tailwind. Giao diện lên hình
# đúng cấu trúc, không có định dạng, và không có bước nào báo lỗi.
COPY tsconfig.json vite.config.ts index.html postcss.config.js tailwind.config.js ./
COPY src ./src
RUN npm run build

# Chặn đúng lỗi đó tái diễn: nếu CSS xuất ra không chứa lớp nền của khung
# ứng dụng thì Tailwind đã không chạy, và build phải đỏ ngay tại đây thay vì
# đẩy một giao diện trắng trơn lên máy chủ.
RUN grep -q -- '--tw-\|bg-panel\|\.bg-app' dist/assets/*.css \
    || (echo "CSS build thiếu utility class của Tailwind — kiểm tra postcss.config.js" && exit 1)

# ---- Stage 2: Phục vụ tệp tĩnh ----
# Bản unprivileged chạy bằng user nginx (uid 101) và nghe cổng 8080,
# không cần root ở bất kỳ bước nào.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1:8080/healthz || exit 1
