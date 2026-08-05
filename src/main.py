import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.fc_routes import router as fc_router
from src.api.routes import router
from src.config import get_settings
from src.db import session as db
from src.models.schemas import HealthOut, ReadyOut
from src.services import queue

logger = logging.getLogger("fin07.api")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logger.info("Khởi động %s ở chế độ %s", settings.app_name, settings.app_env)
    yield
    logger.info("Đang tắt")


app = FastAPI(
    title="FIN-07 AML Agent API",
    description="AI Agent phát hiện rửa tiền và giám sát tuân thủ",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")
# Màn hình "Thành phố tài chính" — đọc schema `fc` do ABM sinh ra.
app.include_router(fc_router, prefix="/api/v1")


@app.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness — tiến trình còn sống. Không chạm phụ thuộc ngoài."""
    return HealthOut(status="ok", env=settings.app_env)


@app.get("/health/ready", response_model=ReadyOut)
async def ready() -> JSONResponse:
    """Readiness — phục vụ được request thật chưa.

    Đây là endpoint mà healthcheck của container dùng: API chỉ xanh khi cả
    PostgreSQL và Redis đều trả lời. Trả 503 khi chưa sẵn sàng để orchestrator
    không đẩy lưu lượng vào.
    """
    checks = {"database": False, "redis": False}
    try:
        checks["database"] = db.ping()
    except Exception as exc:  # noqa: BLE001 — readiness phải báo trạng thái, không ném lỗi
        logger.warning("Readiness: PostgreSQL chưa sẵn sàng: %s", exc)
    try:
        checks["redis"] = queue.ping()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness: Redis chưa sẵn sàng: %s", exc)

    healthy = all(checks.values())
    body = ReadyOut(status="ready" if healthy else "not_ready", **checks)
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())
