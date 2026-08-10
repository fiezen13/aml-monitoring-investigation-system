# Image dùng chung cho hai tiến trình: API và worker. Cùng mã nguồn, khác
# lệnh khởi động (xem docker-compose.yml). Một image thì không có chuyện hai
# tiến trình chạy hai phiên bản mã khác nhau.

# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Mạng chập chờn làm build đỏ mà không phải lỗi của ai. Mặc định 15 giây
    # là quá ngắn cho các gói lớn của langchain.
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# ---- Stage 2: Runtime ----
FROM python:3.11-slim

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Chạy `python scripts/seed_data.py` thì sys.path[0] là /app/scripts chứ
    # không phải /app, nên `import src...` hỏng. Khai báo ở đây một lần thay
    # vì mỗi lệnh gọi phải tự lo.
    PYTHONPATH=/app

WORKDIR /app

# Chạy bằng user thường. venv đặt ở /opt chứ không ở /root: /root chỉ mình
# root vào được, để venv trong đó thì user thường không chạy nổi.
RUN useradd --create-home --uid 10001 appuser

COPY --from=builder /opt/venv /opt/venv

COPY src ./src
COPY scripts ./scripts

# db/init phải nằm trong image, không chỉ trong repo: `scripts/migrate.py` đọc
# các file lược đồ từ đây, và nó luôn chạy BÊN TRONG container — cả `make
# migrate` lẫn đường triển khai Cloud SQL. Thiếu thư mục này, migrate.py chạy
# tới nơi rồi dừng với "Không tìm thấy file .sql nào trong /app/db/init".
#
# Container postgres nạp lược đồ qua bind mount trong docker-compose.yml, một
# đường hoàn toàn khác — nên thiếu sót ở đây không lộ ra khi dựng bằng compose
# ở máy cá nhân.
COPY db ./db

RUN mkdir -p /app/data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Xanh khi API phục vụ được request thật, tức là cả PostgreSQL lẫn Redis đều
# trả lời. /health/ready trả 503 khi chưa sẵn sàng và urlopen ném lỗi.
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready')" || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
