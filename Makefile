.PHONY: help up down restart logs ps health seed seed-verify db-reset db-shell redis-shell \
        build run worker test test-unit lint format typecheck check clean

COMPOSE ?= docker compose

help:  ## Danh sách lệnh
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- Toàn bộ hệ thống ------------------------------------------------

up:  ## Dựng toàn bộ hệ thống và chờ mọi healthcheck xanh
	$(COMPOSE) up -d --build --wait
	@echo ""
	@echo "  Console   http://localhost:$${WEB_PORT:-5173}"
	@echo "  API       http://localhost:$${API_PORT:-8000}/docs"
	@echo "  Readiness http://localhost:$${API_PORT:-8000}/health/ready"

down:  ## Dừng hệ thống, giữ lại dữ liệu
	$(COMPOSE) down

restart:  ## Khởi động lại api và worker (dùng sau khi sửa mã)
	$(COMPOSE) up -d --build api worker

logs:  ## Xem log tất cả dịch vụ
	$(COMPOSE) logs -f --tail=100

ps:  ## Trạng thái các dịch vụ
	$(COMPOSE) ps

health:  ## Trạng thái sức khoẻ từng container
	@for s in postgres redis api worker web; do \
		cid=$$($(COMPOSE) ps -q $$s 2>/dev/null); \
		if [ -z "$$cid" ]; then printf "  %-10s %s\n" "$$s" "chưa chạy"; \
		else printf "  %-10s %s\n" "$$s" "$$(docker inspect -f '{{.State.Health.Status}}' $$cid)"; fi; \
	done

# --- Dữ liệu ---------------------------------------------------------

seed:  ## Nạp lại dữ liệu mẫu (xoá dữ liệu hiện có)
	$(COMPOSE) run --rm seed python scripts/seed_data.py --force

seed-verify:  ## In vân tay dữ liệu mẫu, không ghi cơ sở dữ liệu
	$(COMPOSE) run --rm seed python scripts/seed_data.py --verify

db-reset:  ## Xoá volume PostgreSQL và dựng lại từ db/init (mất toàn bộ dữ liệu)
	$(COMPOSE) down -v
	$(COMPOSE) up -d --wait

db-shell:  ## Mở psql
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fin07} -d $${POSTGRES_DB:-fin07}

redis-shell:  ## Mở redis-cli
	$(COMPOSE) exec redis redis-cli

# --- Chạy ngoài Docker -----------------------------------------------

run:  ## Chạy API bằng venv cục bộ (cần postgres và redis đã lên)
	uvicorn src.main:app --reload --host 0.0.0.0 --port $${API_PORT:-8000}

worker:  ## Chạy worker bằng venv cục bộ
	python -m src.worker.main

build:  ## Build image mà không khởi động
	$(COMPOSE) build

# --- Chất lượng ------------------------------------------------------

test:  ## Chạy toàn bộ kiểm thử
	pytest

test-unit:  ## Chỉ kiểm thử không cần cơ sở dữ liệu
	pytest -m "not integration"

lint:  ## ruff check
	ruff check src tests scripts

format:  ## ruff format
	ruff format src tests scripts

typecheck:  ## Kiểm tra kiểu phía giao diện
	cd web && npm run typecheck

check: lint test  ## Cổng chất lượng chạy trước khi mở pull request
	ruff format --check src tests scripts

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -f coverage.xml .coverage
