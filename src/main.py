import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from src.api.authz import enforce_policy
from src.api.fc_routes import router as fc_router
from src.api.routes import router
from src.config import get_settings
from src.db import session as db
from src.investigation.llm import gemini_health_snapshot, gemini_is_configured
from src.models.schemas import HealthOut, ReadyOut
from src.observability.http import ObservabilityMiddleware
from src.observability.telemetry import initialize_observability, instrument_fastapi
from src.services import queue

logger = logging.getLogger("fin07.api")

settings = get_settings()
initialize_observability(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
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
app.add_middleware(ObservabilityMiddleware)

# Phân quyền gắn ở cấp router: mọi endpoint dưới /api/v1 đều đi qua bảng chính
# sách trong src/api/authz.py trước khi chạy. Các route sức khoẻ và /metrics nằm
# ngoài router nên không bị chặn — chúng phải trả lời được cho orchestrator kể
# cả khi cơ sở dữ liệu phiên đăng nhập chưa sẵn sàng.
_authz = [Depends(enforce_policy)]

app.include_router(router, prefix="/api/v1", dependencies=_authz)
# Màn hình "Thành phố tài chính" — đọc dữ liệu vận hành từ schema `public`.
# Nhánh Bitcoin AML (Elliptic gốc + DFRWS 2026) phục vụ qua fc_router: hàng đợi
# đọc bảng `bitcoin_scored_tx`, giải thích on-demand gọi src/bitcoin_aml/agent.py.
app.include_router(fc_router, prefix="/api/v1", dependencies=_authz)


@app.get("/health", response_model=HealthOut)
@app.get("/health/live", response_model=HealthOut)
async def health() -> HealthOut:
    """Liveness — tiến trình còn sống. Không chạm phụ thuộc ngoài."""
    return HealthOut(status="ok", env=settings.app_env, gemini_configured=gemini_is_configured(settings))


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
    body = ReadyOut(
        status="ready" if healthy else "not_ready",
        gemini_configured=gemini_is_configured(settings),
        **checks,
    )
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump())


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    """Local diagnostic/scrape endpoint; the primary path remains OTLP."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health/gemini")
async def gemini_health() -> dict:
    """Cached provider diagnostic; never calls Gemini and never exposes a key."""
    return gemini_health_snapshot(settings)


instrument_fastapi(app)
