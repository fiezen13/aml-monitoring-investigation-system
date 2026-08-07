# ABM-BANK release runbook

## Prerequisites

Use the repository virtual environment with dependencies from `requirements.txt`. Generated artifacts are ignored by Git. Run commands from the repository root.

## Developer smoke run

```bash
make abm-validate-parameters
make abm-generate-small
make abm-validate-small
```

The tiny release uses 200 customers and 14 days for fast deterministic tests. Repeat generation with the same commit, config, registry, and seed; `logical_world_sha256` must match.
The Make targets pass `--overwrite`, which clears only the exact versioned generated release directory before rebuilding it; omit that flag when an existing artifact must be preserved.

## MVP release

```bash
make abm-release
make abm-validate
make abm-stream-sample
```

The output is `data/generated/ABM-BANK-v0.1.0/`. `data/raw/` is reserved for downloaded source datasets, while `data/generated/` contains reproducible synthetic releases. Review `manifest.json`, all reports, table counts, scenario/control quotas, runtime versions, checksums, and known limitations. `validate` reloads Parquet independently, verifies every manifest checksum, and reruns integrity gates.

## Multi-GB MVP release

```bash
make abm-generate-large
make abm-validate-large
make abm-stream-sample
make abm-ingest-smoke
```

The large output is `data/generated/ABM-BANK-v0.2.0/`. It is split into 128 independently generated and validated shards under `shards/`; each shard uses an ID namespace so primary keys cannot collide across shards. The aggregate manifest enforces a minimum physical size of 3,000,000,000 bytes. If a build is interrupted, `make abm-resume-large` keeps every shard with a passing quality report and regenerates only missing or failed shards.

## Release layout

- `bank_view/`: feature-visible canonical Parquet, with transactions partitioned by event month;
- `ground_truth/`: entity/transaction labels, scenarios, networks, controls, and splits;
- `hidden/`: causal actions and true coordination, restricted from feature pipelines;
- `metadata/`: exact config and registry snapshots;
- `reports/`: quality, statistical, behavioral, and graph results;
- `manifest.json`: identity, provenance, counts, hashes, runtime, and limitations.

## Event adapter and ingestion boundary

`make abm-stream-sample` writes label-free `bank.transaction.posted.v1` JSONL. `make abm-ingest-smoke` creates an isolated Kafka topic and HDFS path, publishes 1,000 canonical CloudEvents, runs the Flink ingestion job, and verifies acknowledgements, record counts, unique IDs, null labels, and absence of hidden fields. It performs ingestion only: no feature fitting, model training, scoring, alerting, or customer decisioning. The adapter rejects ground-truth columns.

## Approval checklist

Approve only when parameter validation, deterministic tests, schema/foreign-key/temporal/accounting checks, leakage checks, scenario and hard-negative quota checks, behavioral and graph suitability, and manifest verification pass. Record the Git commit and archive the artifact outside Git. A release with a changed config, registry, source profile, seed, or code requires a new version or build identity.
