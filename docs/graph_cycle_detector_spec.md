# Graph CYCLE Detector Spec — FIN-07

**Status:** v1.1 — Phase 3 topology/witness materialization optimization implemented and profiled on a real train snapshot; no caps/sharding added.
**Scope:** `CYCLE` detector only (length 2–6, temporal witness, canonicalize, evidence).  
**Does not invent:** FAN/GATHER thresholds, GT matching, sample-volume policy, CYCLE perf hard caps (OPEN #3–#5).

The real-data smoke uses the Phase 1 SCC/core enumeration and Phase 2 temporal witness search. Phase 3 keeps topology construction separate from transaction-edge materialization: transactions are materialized only for directed pairs belonging to enumerated candidate cycles. No degree pruning, motif cap, or sharding is used, so detector semantics are unchanged.

---

## 1. Purpose

Emit:

```text
data/processed/graph_detection_v1.parquet   # account-level signals (CYCLE rows)
data/processed/graph_evidence_v1.jsonl      # motif evidence (CYCLE lines)
```

for temporal-consistent directed simple cycles in the same 7d half-open snapshot window as graph features.

---

## 2. Input

| Artifact | Use |
|----------|-----|
| `data/processed/aml.duckdb` → `transaction` | Edges |
| `data/processed/split_cutoffs.json` | `sample_split` |
| Helpers | `src/data/snapshot_split.py` |

**Required columns:** `transaction_id`, `occurred_at`, `from_account_key`, `to_account_key`  
**Optional (hop metrics):** `amount`  
**Forbidden:** `label_*`, Patterns / IBM GT as detector inputs

**Window:** same as `docs/graph_feature_spec.md` §4.

**Snapshot dates (default until OPEN #5):** candidate dates from data range (same rule as features).

---

## 3. ID semantics

| ID | Meaning |
|----|---------|
| `pattern_instance_id` | Motif = canonical account cycle in `(as_of_ts, window, detector_version)` — **not** witness TX set |
| `evidence_id` | Chosen witness package for that motif (baseline 1–1 with PI) |
| `detection_id` | One participant account exposed to the motif |

```text
motif_key = as_of_ts | window | detector_version | CYCLE | ",".join(accounts)
pattern_instance_id = "PI_CYCLE_" + sha1(motif_key)[:16]

witness_key = pattern_instance_id | ",".join(hop.transaction_id)
evidence_id = "EV_CYCLE_" + sha1(witness_key)[:16]

detection_id = "DET_CYCLE_" + sha1(pattern_instance_id + "|" + account_key)[:16]
```

---

## 4. Two orderings (must not conflate)

| Field | Order |
|-------|--------|
| `accounts` | Lex-smallest **node** rotation (motif identity). No time claim. |
| `hops` | **Temporal witness** order: `occurred_at` non-decreasing. Traceable TX path. |
| `transaction_ids` | Mirror of `hops[*].transaction_id` |

Rotating nodes for canonicalize must **not** reorder `hops`.

---

## 5. Algorithm

1. Build the unique directed topology on window `W` (without allocating per-transaction edge objects).
2. Enumerate simple directed cycles length `L ∈ [2, 6]`; dedupe by canonical account tuple.
3. Materialize the multi-edge transaction lists only for directed pairs used by candidate cycles.
4. For each cycle, search one TX per hop such that some cyclic shift is time-non-decreasing; pick min lex `(t1..tk, id1..idk)` in that shifted order → `hops`.
4. Independently set `accounts` = lex-smallest node rotation.
5. Emit 1 evidence line + `L` detection rows.

No multi-edge collapse via `min`/`max` timestamp per pair.

**OPEN #4:** do not hard-code motif caps as business truth; measure in smoke first.

---

## 6. Output schemas

### Detection parquet columns

`detection_id`, `pattern_instance_id`, `evidence_id`, `account_key`, `as_of_ts`, `snapshot_date`, `window`, `sample_split`, `detected_pattern`, `detector_version`, `cycle_length`

### Evidence JSONL

See final contract: includes `accounts`, `hops[]` (`from_account_key`, `to_account_key`, `transaction_id`, `occurred_at`, `amount`), `transaction_ids`, `duration_hours`, metadata.

---

## 7. Unit tests required

Topology-only without witness → no emit; multi-edge plan example; equal timestamps OK; three start vertices → one PI / three DET; length 2 and 6 OK, 7 no; window bounds; sample_split; determinism; canonical vs witness order diverge; hops traceable; no `label_*`.

---

## 8. Out of scope

FAN_IN / FAN_OUT / GATHER_SCATTER, `graph_score`, GT matching, full 6.1M run without perf smoke.

---

*Spec v1.0 — CYCLE only.*
