.PHONY: help up down restart logs ps health db-reset db-shell redis-shell behavior-batch behavior-train \
        train-fusion load-fusion load-edge-release \
        migrate migrate-status \
        build run worker test test-unit contracts-check lint format typecheck check clean \
        aml-up aml-down aml-status aml-topics aml-fixture aml-producer-sample aml-producer-run \
        aml-producer-eventtime aml-producer-resume aml-flink-build aml-flink-test aml-submit \
        aml-cancel aml-inspect-kafka aml-inspect-hdfs aml-patterns aml-smoke aml-logs \
        obs-up obs-down obs-status obs-logs obs-reload

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

migrate:  ## Áp các file lược đồ trong db/init còn thiếu (giữ nguyên dữ liệu)
	$(COMPOSE) run --rm migrate python scripts/migrate.py

migrate-status:  ## Liệt kê file lược đồ nào đã áp, file nào còn chờ
	$(COMPOSE) run --rm migrate python scripts/migrate.py --status

db-reset:  ## Xoá volume PostgreSQL và dựng lại từ db/init (mất toàn bộ dữ liệu)
	$(COMPOSE) down -v
	$(COMPOSE) up -d --wait

db-shell:  ## Mở psql
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fin07} -d $${POSTGRES_DB:-fin07}

redis-shell:  ## Mở redis-cli
	$(COMPOSE) exec redis redis-cli

behavior-batch:  ## Chạy Behaviour ML PoC; FILE=transactions.csv trong data/batch/ (SUBJECTS=... giới hạn tài khoản được chấm điểm)
	@test -n "$(FILE)" || (echo "Thiếu FILE. Ví dụ: make behavior-batch FILE=transactions.csv" && exit 2)
	$(COMPOSE) --profile batch run --rm behavior-batch \
		--input "/input/$(FILE)" \
		$(if $(SUBJECTS),--subject-accounts "/input/$(SUBJECTS)",) \
		--window "$${BEHAVIOR_WINDOW:-7d}" \
		--threshold "$${BEHAVIOR_THRESHOLD:-0.70}" \
		--top-k "$${BEHAVIOR_TOP_K:-100}"

behavior-train:  ## Huấn luyện + đánh giá Isolation Forest rolling 7d trên DuckDB full
	python scripts/train_behavior_7d.py \
		--db data/processed/aml.duckdb \
		--output-dir data/processed/behavior-7d \
		--reports-dir reports/behavior-7d \
		--require-full-li-small

train-fusion:  ## Retrain IF + Graph, chọn champion trên validation và tạo fusion v2
	.venv/bin/python scripts/train_fusion_v2.py

load-fusion:  ## Nạp LI-Small + kết quả champion fusion v2 vào PostgreSQL (idempotent)
	.venv/bin/python scripts/load_fusion_release.py

load-edge-release:  ## Nạp currency-native HI-Medium release vào PostgreSQL rỗng
	.venv/bin/python scripts/load_currency_native_edge_release.py

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

contracts-check:  ## Kiểm chứng mọi hợp đồng dữ liệu trong contracts/
	pytest tests/test_contracts -q

lint:  ## ruff check
	ruff check src tests scripts

format:  ## ruff format
	ruff format src tests scripts

typecheck:  ## Kiểm tra kiểu phía giao diện
	cd web && npm run typecheck

check: lint test  ## Cổng chất lượng chạy trước khi mở pull request
	ruff format --check src tests scripts

# --- Luồng nạp dữ liệu AML (CSV → Kafka → Flink → HDFS) --------------
#
# Tất cả nằm trong profile `aml` của docker-compose.yml, không chạy cùng
# `make up`. Hướng dẫn đầy đủ: contracts/ingestion/README.md

AML := $(COMPOSE) --profile aml

aml-up:  ## Dựng Kafka, HDFS, Flink và chờ xanh
	$(AML) up -d --build --wait kafka kafka-ui namenode datanode flink-jobmanager flink-taskmanager
	$(AML) up hdfs-init
	@$(MAKE) --no-print-directory aml-topics
	@echo ""
	@echo "  Flink UI     http://localhost:$${AML_FLINK_UI_PORT:-8081}"
	@echo "  HDFS UI      http://localhost:$${AML_HDFS_UI_PORT:-9870}"
	@echo "  Kafka UI     http://localhost:$${AML_KAFKA_UI_PORT:-8082}"
	@echo "  Kafka        localhost:$${AML_KAFKA_PORT:-29092}"

aml-down:  ## Dừng luồng AML, giữ dữ liệu
	$(AML) down

aml-status:  ## Trạng thái các dịch vụ AML
	@for s in kafka kafka-ui namenode datanode flink-jobmanager flink-taskmanager; do \
		cid=$$($(AML) ps -q $$s 2>/dev/null); \
		if [ -z "$$cid" ]; then printf "  %-20s %s\n" "$$s" "chưa chạy"; \
		else printf "  %-20s %s\n" "$$s" "$$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $$cid)"; fi; \
	done

aml-logs:  ## Log của Flink và Kafka
	$(AML) logs -f --tail=100 flink-jobmanager flink-taskmanager kafka

aml-topics:  ## Tạo topic Kafka (chạy lại an toàn)
	$(AML) run --rm kafka-init

aml-fixture:  ## Sinh lại file CSV mẫu dùng cho kiểm thử
	python scripts/aml/make_fixture.py

aml-producer-sample:  ## Phát 1.000 giao dịch đầu tiên vào Kafka
	$(AML) run --rm aml-producer --max-records 1000 --no-resume

aml-producer-run:  ## Phát toàn bộ file (không giới hạn)
	$(AML) run --rm aml-producer --max-records 0

aml-producer-eventtime:  ## Phát lại theo thời gian gốc, nhanh gấp 100 lần
	$(AML) run --rm aml-producer --mode event-time --speed 100 --max-records 0

aml-producer-resume:  ## Chạy tiếp từ điểm dừng của lần trước
	$(AML) run --rm aml-producer --max-records 0

aml-flink-build:  ## Build jar job Flink (cần JDK 11 và Maven trên máy)
	cd flink/aml-ingestion && mvn -B -DskipTests package

aml-flink-test:  ## Chạy kiểm thử đơn vị của job Flink
	cd flink/aml-ingestion && mvn -B test

aml-submit:  ## Nộp job Flink lên cụm
	./scripts/aml/submit_job.sh

aml-cancel:  ## Dừng job Flink đang chạy
	./scripts/aml/cancel_job.sh

aml-inspect-kafka:  ## Xem topic, offset và vài message
	./scripts/aml/inspect_kafka.sh

aml-inspect-hdfs:  ## Xem phân vùng và số file trên HDFS
	./scripts/aml/inspect_hdfs.sh

aml-patterns:  ## Chép *_Patterns.txt lên HDFS, nguyên trạng
	./scripts/aml/copy_patterns_to_hdfs.sh

aml-smoke:  ## Kiểm tra khói đầu–cuối bằng file mẫu
	./scripts/aml/smoke_test.sh

# --- Observability correlated (OTel + Prometheus + Loki + Jaeger) -----
#
# Profile `obs`, không chạy cùng `make up`. Cổng bind vào 127.0.0.1 nên
# không ra Internet. Hướng dẫn đầy đủ: docs/operations/MONITORING.md

OBS := $(COMPOSE) --profile obs

obs-up:  ## Dựng core app và full correlated observability stack
	OTEL_ENABLED=true $(OBS) up -d --build --wait
	@echo ""
	@echo "  Cockpit     http://localhost:$${WEB_PORT:-5173}/models   (đăng nhập FIN-07)"
	@echo "  Grafana     http://localhost:$${GRAFANA_PORT:-3000}   (admin trực tiếp)"
	@echo "  Prometheus  http://localhost:$${PROMETHEUS_PORT:-9090}"
	@echo "  Jaeger      http://localhost:$${JAEGER_UI_PORT:-16686}"

obs-down:  ## Dừng cụm observability, giữ dữ liệu đã thu
	$(OBS) stop prometheus grafana loki jaeger otel-collector cadvisor node-exporter redis-exporter postgres-exporter

obs-status:  ## Mục tiêu nào Prometheus đang scrape được
	@curl -s http://localhost:$${PROMETHEUS_PORT:-9090}/api/v1/targets \
		| python3 -c "import json,sys; [print('  %-18s %-28s %s' % (t['labels']['job'], t['labels']['instance'], t['health'])) for t in json.load(sys.stdin)['data']['activeTargets']]" \
		2>/dev/null || echo "  Prometheus chưa chạy — make obs-up"

obs-logs:  ## Log của telemetry gateway và backends
	$(OBS) logs -f --tail=100 otel-collector prometheus loki jaeger grafana

obs-reload:  ## Nạp lại cấu hình Prometheus, không khởi động lại container
	@curl -fsS -X POST http://localhost:$${PROMETHEUS_PORT:-9090}/-/reload && echo "  Đã nạp lại cấu hình"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name .ruff_cache -exec rm -rf {} +
	rm -f coverage.xml .coverage
