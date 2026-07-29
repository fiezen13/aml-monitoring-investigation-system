# ---- Stage 1: Build ----
FROM node:22-alpine AS builder

WORKDIR /app

# Copy manifest trước để lớp cài đặt phụ thuộc được cache riêng: sửa mã nguồn
# không làm cài lại node_modules.
COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

# ---- Stage 2: Phục vụ tệp tĩnh ----
# Bản unprivileged chạy bằng user nginx (uid 101) và nghe cổng 8080,
# không cần root ở bất kỳ bước nào.
FROM nginxinc/nginx-unprivileged:1.27-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1:8080/healthz || exit 1
