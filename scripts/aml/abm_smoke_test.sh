#!/usr/bin/env bash
# End-to-end ABM Bank View smoke test: Parquet -> Kafka -> Flink -> HDFS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
source "${REPO_ROOT}/ci/lib.sh"
cd "$REPO_ROOT"

COMPOSE="${COMPOSE:-docker compose}"
AML="$COMPOSE --profile aml"
RELEASE="${ABM_RELEASE_PATH:-data/generated/ABM-BANK-v0.2.0}"
EXPECTED="${ABM_SMOKE_RECORDS:-1000}"
RUN_ID="$(date +%s)"
TOPIC="bank.abm.smoke.${RUN_ID}"
GROUP_ID="bank-abm-smoke-${RUN_ID}"
HDFS_BASE="/data/abm_smoke/${RUN_ID}"
HDFS_URI="hdfs://namenode:8020${HDFS_BASE}"
REPORT_DIR="data/generated/ingestion_reports"
REPORT_PATH="${REPORT_DIR}/ABM-BANK-ingestion-${RUN_ID}.json"

cleanup() {
    "${SCRIPT_DIR}/cancel_job.sh" >/dev/null 2>&1 || true
    $AML exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
        --delete --topic "$TOPIC" >/dev/null 2>&1 || true
    $AML exec -T namenode hdfs dfs -rm -r -f "$HDFS_BASE" >/dev/null 2>&1 || true
}
trap cleanup EXIT

need docker
need .venv/bin/python
[ -f "${RELEASE}/manifest.json" ] || die "Không thấy release ${RELEASE}"

if command -v mvn >/dev/null 2>&1; then
    mvn -B -q -f flink/aml-ingestion/pom.xml package
    export AML_FLINK_DOCKERFILE=docker/flink/Dockerfile.prebuilt
fi

group_start "1/6 Hạ tầng Kafka, Flink và HDFS"
$AML up -d --build --wait kafka namenode datanode flink-jobmanager flink-taskmanager \
    || die "Không dựng được hạ tầng ingest"
$AML exec -T namenode hdfs dfsadmin -safemode wait >/dev/null \
    || die "NameNode không thoát safe mode"
$AML up hdfs-init >/dev/null 2>&1 || true
ok "Hạ tầng ingest đã healthy"
group_end

group_start "2/6 Topic và HDFS riêng cho smoke test"
$AML exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 \
    --create --if-not-exists --topic "$TOPIC" --partitions 3 --replication-factor 1 >/dev/null
$AML exec -T namenode hdfs dfs -mkdir -p "$HDFS_BASE"
$AML exec -T namenode hdfs dfs -chmod -R 777 "$HDFS_BASE"
ok "Topic ${TOPIC} và ${HDFS_BASE} đã sẵn sàng"
group_end

group_start "3/6 Nộp Flink ingestion job"
"${SCRIPT_DIR}/cancel_job.sh" >/dev/null 2>&1 || true
AML_JOB_JAR=/opt/flink/usrlib/aml-ingestion.jar "${SCRIPT_DIR}/submit_job.sh" \
    --aml.hdfs.base.path "$HDFS_URI" \
    --aml.hdfs.format json \
    --aml.raw.topic "$TOPIC" \
    --aml.group.id "$GROUP_ID" \
    --aml.checkpoint.interval.ms 10000 \
    --aml.rollover.interval.ms 15000 \
    --aml.rollover.inactivity.ms 10000 \
    --aml.offset.reset earliest \
    || die "Không nộp được Flink job"
group_end

group_start "4/6 Publish sự kiện ABM vào Kafka"
publish_output="$(.venv/bin/python -m abm publish \
    --release "$RELEASE" \
    --bootstrap-servers localhost:29092 \
    --topic "$TOPIC" \
    --limit "$EXPECTED")"
echo "$publish_output"
acked="$(echo "$publish_output" | .venv/bin/python -c 'import json,sys; print(json.load(sys.stdin)["acked"])')"
[ "$acked" -eq "$EXPECTED" ] || die "Kafka ack ${acked}, mong đợi ${EXPECTED}"
topic_count="$($AML exec -T kafka /opt/kafka/bin/kafka-get-offsets.sh \
    --bootstrap-server localhost:9092 --topic "$TOPIC" | awk -F: '{sum += $3} END {print sum + 0}')"
[ "$topic_count" -eq "$EXPECTED" ] || die "Kafka có ${topic_count} message, mong đợi ${EXPECTED}"
ok "Kafka xác nhận đủ ${acked} sự kiện"
group_end

group_start "5/6 Flink ghi HDFS và đối chiếu dữ liệu"
records=0
payload="$(mktemp)"
for attempt in $(seq 1 36); do
    $AML exec -T namenode bash -c \
        "hdfs dfs -cat '${HDFS_BASE}/bronze/transactions/source_dataset=*/event_date=*/event_hour=*/*.jsonl' 2>/dev/null" \
        >"$payload" || true
    records="$(wc -l <"$payload" | tr -d ' ')"
    if [ "$records" -eq "$EXPECTED" ]; then
        break
    fi
    sleep 5
done
[ "$records" -eq "$EXPECTED" ] || die "HDFS có ${records} bản ghi, mong đợi ${EXPECTED}"
distinct="$(grep -o '"transaction_id":"[^"]*"' "$payload" | sort -u | wc -l | tr -d ' ')"
null_labels="$(grep -c '"is_laundering":null' "$payload" || true)"
hidden_fields="$(grep -Ec 'scenario_instance_id|network_id|hidden_intent|true_controller_id' "$payload" || true)"
[ "$distinct" -eq "$EXPECTED" ] || die "Chỉ có ${distinct}/${EXPECTED} transaction_id duy nhất"
[ "$null_labels" -eq "$EXPECTED" ] || die "Có label thật lọt vào HDFS: null=${null_labels}/${EXPECTED}"
[ "$hidden_fields" -eq 0 ] || die "Có ${hidden_fields} dòng chứa trường hidden"
ok "HDFS có ${records} bản ghi duy nhất, label null, không lộ hidden state"
group_end

group_start "6/6 Ghi báo cáo smoke test"
mkdir -p "$REPORT_DIR"
release_fingerprint="$(.venv/bin/python -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m.get("logical_dataset_sha256") or m.get("logical_world_sha256"))' "${RELEASE}/manifest.json")"
.venv/bin/python - "$REPORT_PATH" "$RUN_ID" "$RELEASE" "$TOPIC" "$HDFS_BASE" "$EXPECTED" "$release_fingerprint" <<'PY'
import json
import sys
from datetime import datetime
from pathlib import Path

path, run_id, release, topic, hdfs_base, records, fingerprint = sys.argv[1:]
report = {
    "status": "PASS",
    "tested_at": datetime.now().astimezone().isoformat(),
    "run_id": run_id,
    "release": str(Path(release).resolve()),
    "release_fingerprint": fingerprint,
    "kafka_topic": topic,
    "kafka_acked": int(records),
    "hdfs_path": hdfs_base,
    "hdfs_records": int(records),
    "distinct_transaction_ids": int(records),
    "laundering_labels_exposed": 0,
    "hidden_fields_exposed": 0,
    "flow": ["ABM Parquet", "canonical CloudEvent", "Kafka", "Flink", "HDFS JSONL"],
}
Path(path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
ok "Báo cáo: ${REPORT_PATH}"
group_end
