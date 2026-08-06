# Kafka-Flink-HDFS pipeline audit scope

Status: Phase 1 safety baseline  
Audit date: 2026-08-06 (Asia/Ho_Chi_Minh)  
Owner: Bảo — PM / Solution Architect / DevOps  
Repository: `P-022`  
Branch: `develop`  
Audited commit: `c8895e1` (`origin/develop`)  

## Safety baseline

- `git status --short --branch` reported `## develop...origin/develop`; the working tree was clean before this audit.
- The current and requested base branch are both `develop`.
- No files were moved or deleted. No pipeline architecture, public schema, behavioral ML, graph ML, frontend design, or generated data was changed before this document was created.
- The relevant implementation was introduced primarily by commit `9fb4972` (`feat(aml): nạp dữ liệu IBM AML từ CSV qua Kafka và Flink xuống HDFS`). Recent repository-standardization commits moved the ingestion contract into `contracts/ingestion/` and removed the former `docs/AML_INGESTION.md`.
- The supplied CI evidence shows the ordinary application compose smoke job reached the frontend check and failed because `ci/smoke.sh` searched for obsolete text. This is separate from the AML ingestion profile.

## In scope

- Python CSV replay producer in `src/aml/`.
- The versioned ingestion contract in `contracts/ingestion/`.
- Kafka broker, raw topic, producer DLQ topic, keys, acknowledgements, retry/idempotence configuration, retention, and offsets.
- Java Flink job in `flink/aml-ingestion/`, including parsing, validation, event time, watermarking, checkpoints, restart behavior, Kafka source, and HDFS sinks.
- Kafka, Flink, Hadoop/HDFS, and producer services in the root `docker-compose.yml` AML profile.
- Flink image build in `docker/flink/`.
- AML Make targets and `scripts/aml/` operational scripts.
- Existing Python and Java ingestion tests and the end-to-end smoke script.
- Environment-variable documentation, ignored generated state, local secret handling, and repository secret hygiene.
- The narrowly scoped current CI smoke assertion shown failing in the supplied screenshots.

## Out of scope for this phase

- Kafka-Flink-HDFS baseline ingest, restart, replay, and destructive cleanup execution. These belong to later phases.
- Production-scale multi-node Kafka, Flink HA, HDFS HA, Kubernetes, autoscaling, or new infrastructure products.
- Behavioral ML, graph ML, feature-platform, detection, and agent-runtime implementations.
- Backend API contract changes and frontend redesign.
- Public event-schema changes. The existing ingestion schema remains version `1.0`.
- Rewriting Git history. A credential-like committed value is reported, but any history cleanup must be coordinated after rotation.

## Detected versions

| Component | Version used by the repository | Evidence |
|---|---:|---|
| Kafka | 3.9.1 | `apache/kafka:3.9.1` for `kafka` and `kafka-init` in `docker-compose.yml` |
| Flink | 1.20.1, Scala 2.12, Java 11 | `flink:1.20.1-scala_2.12-java11` in `docker/flink/Dockerfile`; `flink.version=1.20.1` in the Maven POM |
| Flink Kafka connector | 3.3.0-1.20 | `flink.kafka.connector.version` in `flink/aml-ingestion/pom.xml` |
| Hadoop/HDFS | 3.3.6 | NameNode, DataNode, and Hadoop build stage use `apache/hadoop:3.3.6` |
| Java | 11 | Maven compiler release and Flink runtime are Java 11; audit host has OpenJDK 11.0.27 |
| Python | 3.11 in image and CI | Root `Dockerfile` uses `python:3.11-slim`; GitHub Actions sets Python 3.11. Audit host has Python 3.13.8 |
| Maven | 3.9 image family; 3.9.9 on audit host | Flink builder uses `maven:3.9-eclipse-temurin-11`; host reports Maven 3.9.9 |
| Docker | client 29.5.3 | `docker --version` on the audit host |
| Docker Compose | v5.1.4 | `docker compose version` on the audit host |

Image tags are pinned to concrete component versions but not immutable image digests.

## How the pipeline starts today

The AML data platform is an opt-in Compose profile and is not started by ordinary `docker compose up`.

```bash
make aml-up
make aml-submit
make aml-producer-sample
```

Equivalent implementation-level commands are:

```bash
docker compose --profile aml up -d --build --wait kafka namenode datanode flink-jobmanager flink-taskmanager
docker compose --profile aml up hdfs-init
docker compose --profile aml run --rm kafka-init
./scripts/aml/submit_job.sh
docker compose --profile aml run --rm aml-producer --max-records 1000 --no-resume
```

`make aml-smoke` is the existing infrastructure-dependent end-to-end test. It creates per-run Kafka topics, a per-run HDFS base path, and a per-run consumer group, then deletes those temporary resources on exit.

## Environment and secret handling

Tracked environment templates:

- `.env.example` — root application and AML settings.
- `jenkins/.env.example` — Jenkins bootstrap/deployment settings.
- `web/.env.example` — Vite settings.

Local environment files:

- Root `.env` exists locally and is ignored by `.gitignore`. Only variable names were inspected; values were not printed or copied into this audit.
- `docker-compose.yml` treats the root `.env` as optional and supplies local-development defaults.
- Python `AmlSettings` also loads `.env` through `pydantic-settings`.
- GitHub Actions obtains registry authentication from `GITHUB_TOKEN`; Jenkins documents credentials through its untracked environment file.

Security exception: `.env.example:192` and the prior repository audit contained a committed non-placeholder API credential-like value. It has existed since the initial commit. The value is intentionally not reproduced here and has now been removed from the current working tree. It must still be rotated/revoked outside Git and assessed for coordinated history cleanup. See `PIPELINE_GAP_REPORT.md` gap `DP-001`.

## Test environment

- Host: macOS 26.5.2, Darwin 25.5.0, Apple Silicon (`arm64`).
- Docker CLI and Compose are installed.
- Docker daemon was not running during the initial Phase 1 inspection (`failed to connect to the docker API`). It was subsequently started and the isolated default-profile application Compose smoke test passed on 2026-08-06. The AML profile itself was not started, so no claim about Kafka/Flink/HDFS runtime health, checkpoint completion, or end-to-end delivery is made in this phase.
- Static Compose rendering works: the AML profile resolves the expected services and named volumes.
- The repository notes that the Hadoop image is `linux/amd64`, so local Apple Silicon execution requires emulation.

## Assumptions

- The root `docker-compose.yml` is the authoritative local data-platform topology because all AML Make targets and scripts use it.
- Default environment values describe the supported local development path; production guarantees cannot be inferred from this single-node profile.
- `transaction_id` is the current contract's deterministic event identifier. The audit does not rename it to `event_id` because that would be a public schema change.
- Kafka offsets committed by the Flink source and producer CSV checkpoints are different mechanisms and must not be treated as one recovery boundary.

## Known limitations at the end of Phase 1

- No fresh ingest, component restart, replay, savepoint, or recovery test has yet been executed.
- Docker runtime evidence from the original ingestion commit is historical evidence, not proof of the current commit.
- No Schema Registry exists; schema compatibility is implemented by a JSON Schema plus Python and Java code.
- The current local platform deliberately has one Kafka broker, one JobManager, one TaskManager, one HDFS NameNode, and one DataNode.
- Delivery semantics for the complete CSV producer -> Kafka -> Flink -> HDFS path are not proven exactly-once. The safe current conclusion is at-least-once end-to-end with possible duplicate `transaction_id` values in bronze.
