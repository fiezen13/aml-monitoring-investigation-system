# Graph Feature Spec — FIN-07

**Status:** v1.0 — locked formulas from `docs/graph_branch_plan.md` v0.5
**Scope:** Graph **features only** (8 measurements + cold-start metadata). **No detectors** in this document.
**Source of truth (architecture):** `docs/graph_branch_plan.md`
**Does not invent:** FAN/GATHER thresholds, GT matching, `graph_score`, CYCLE detector, sample-volume subsample policy beyond the default candidate-date rule below.

---

## 1. Purpose

Define exact input, sample identity, windowing, `sample_split`, formulas, cold-start policy, output schema, and unit tests for:

```text
data/processed/graph_features_v1.parquet
```

Implementation must match this spec. If something is unmarked here and listed as **open** in the plan, do **not** invent it — escalate.

---

## 2. Input

### 2.1. Artifacts

| Artifact | Path |
|----------|------|
| Canonical DB | `data/processed/aml.duckdb` |
| Split cutoffs | `data/processed/split_cutoffs.json` |
| Column SoT | `src/data/schemas.py` |

Do **not** read raw IBM CSV for this pipeline. Do **not** overwrite `aml.duckdb`.

### 2.2. Tables / columns used

**From `transaction` (required for features):**

| Column | Use |
|--------|-----|
| `occurred_at` | Window / lookback filters (UTC timestamptz) |
| `from_account_key` | Outgoing / edge source |
| `to_account_key` | Incoming / edge destination |
| `amount` | Outbound USD weight |
| `amount_received` | Inbound USD weight |

**Allowed but not used as feature inputs:** `transaction_id`, `channel`, amount/currency originals, `split` (transaction-level), `label_laundering`.

**Forbidden as features:** any `label_*` column; Patterns.txt / typology labels.

**From `account` (optional):** may be used only to enumerate known keys; samples are defined by activity in-window, not by full account dimension alone.

### 2.3. Cutoffs file fields used

From `split_cutoffs.json`:

| Field | Example (current processed run) |
|-------|----------------------------------|
| `train_end_ts` | `2022-09-06 23:43:00+00:00` |
| `val_end_ts` | `2022-09-08 21:12:00+00:00` |

Parse as timezone-aware UTC datetimes for comparisons with `as_of_ts`.

---

## 3. Sample identity

### 3.1. Keys

```text
sample identity = (account_key, as_of_ts, window)
window          = "7d"   # baseline Graph scoring window (string literal)
```

| Field | Type | Definition |
|-------|------|------------|
| `account_key` | string | Task 1 key `bank:account` |
| `as_of_ts` | timestamptz UTC | `end_ts` of the snapshot (exclusive upper bound) |
| `window` | string | always `"7d"` for this baseline artifact |
| `snapshot_date` | date (UTC) | calendar date `D` of the snapshot |
| `sample_split` | string | `train` \| `val` \| `test` from §5 |

### 3.2. Who gets a row?

Emit a feature row for `(account_key, as_of_ts, "7d")` **iff** the account has **≥ 1** transaction in the scoring window where:

```text
from_account_key = account_key  OR  to_account_key = account_key
```

and that transaction satisfies the half-open window predicate (§4).

---

## 4. Half-open 7d window

For each UTC calendar **snapshot date** `D`:

```text
end_ts   = datetime(D + 1 day, 00:00:00, tz=UTC)
start_ts = end_ts - 7 days
as_of_ts = end_ts
```

**Scoring window** (transactions used for degree / money / neighbor features):

```text
start_ts <= occurred_at < end_ts
```

**Example** (`D = 2022-09-09`):

```text
start_ts = 2022-09-03T00:00:00+00:00
end_ts   = 2022-09-10T00:00:00+00:00
as_of_ts = 2022-09-10T00:00:00+00:00

include:  start_ts <= occurred_at < end_ts
```

**Hard rules:**

- Never use `occurred_at >= end_ts`.
- Do not use `23:59:59` end-of-day inclusive convention.
- Must match Isolation Forest handoff (`docs/isolation_forest_handoff.md`) for the same `as_of_ts` / 7d fusion key.

### 4.1. Candidate snapshot dates `D` (default)

**Default (until sample-volume decision is closed differently):**

Let `t_min = min(occurred_at)`, `t_max = max(occurred_at)` over `transaction`.

Candidate `D` = every UTC calendar date from `date_utc(t_min)` through `date_utc(t_max)` inclusive, such that the window `[start_ts, end_ts)` can contain data (i.e. `start_ts < t_max` and `end_ts > t_min`).

**Open (plan):** whether to subsample dates/accounts for artifact size — **not invented here**. Default = full candidate set above unless a reviewed config says otherwise.

---

## 5. `sample_split`

### 5.1. Helper (shared with IF)

```text
assign_snapshot_split(as_of_ts, split_cutoffs) -> {"train","val","test"}

train_end_ts = parse_utc(split_cutoffs["train_end_ts"])
val_end_ts   = parse_utc(split_cutoffs["val_end_ts"])

if as_of_ts <= train_end_ts:
    return "train"
elif as_of_ts <= val_end_ts:
    return "val"
else:
    return "test"
```

Planned code location (from plan): `src/data/snapshot_split.py` (or equivalent single shared module). Graph and IF **must** call the same function.

### 5.2. Semantics

- Split is by **`as_of_ts`**, **not** by mix of `transaction.split` inside the window.
- A val/test snapshot **may** include historical train (and for test: train+val) transactions with `occurred_at < end_ts`.
- **Forbidden:** drop samples because the window mixes Task 1 tx splits; assign split by majority tx split.

### 5.3. Downstream use

| `sample_split` | Allowed use |
|----------------|-------------|
| `train` | Fit / calibrate anything that learns from Graph features later; FAN EDA thresholds (detectors — out of scope here) |
| `val` | Tune |
| `test` | Final report |

---

## 6. Notation for one sample

Fix `account_key = A`, `as_of_ts = end_ts`, `start_ts = end_ts - 7d`.

**In-window set** `W`:

```text
W = { tx | start_ts <= tx.occurred_at < end_ts }
```

**Inbound counterparties**

```text
in_set(A)  = { tx.from_account_key | tx ∈ W, tx.to_account_key = A }
```

**Outbound counterparties**

```text
out_set(A) = { tx.to_account_key   | tx ∈ W, tx.from_account_key = A }
```

(Unique sets — each counterparty counted once.)

**History set** `H` (for new-counterparty + cold-start):

```text
H = { tx | tx.occurred_at < start_ts,
           (tx.from_account_key = A OR tx.to_account_key = A) }
```

**Historical inbound counterparties**

```text
hist_in(A)  = { tx.from_account_key | tx.occurred_at < start_ts, tx.to_account_key = A }
```

**Historical outbound counterparties**

```text
hist_out(A) = { tx.to_account_key   | tx.occurred_at < start_ts, tx.from_account_key = A }
```

---

## 7. Exact formulas — 8 graph features

All features are computed only from Task 1 columns listed in §2.2.
No `label_*`. No Patterns.

### 7.1. `in_degree_7d`

```text
in_degree_7d = |in_set(A)|
```

No inbound → `0`.

### 7.2. `out_degree_7d`

```text
out_degree_7d = |out_set(A)|
```

No outbound → `0`.

### 7.3. `unique_neighbors_7d`

```text
unique_neighbors_7d = |in_set(A) ∪ out_set(A)|
```

Same neighbor in and out → counted once.

### 7.4. `in_out_degree_ratio_7d`

```text
in  = in_degree_7d
out = out_degree_7d

if in == 0 and out == 0:
    in_out_degree_ratio_7d = 0
else:
    in_out_degree_ratio_7d = (in - out) / (in + out)
```

Range: `[-1, 1]`. Never `inf` / `NaN` from this formula.

### 7.5. `new_in_counterparty_ratio_7d`

```text
n_in = |in_set(A)|
n_new_in = |{ cp ∈ in_set(A) | cp ∉ hist_in(A) }|

if n_in == 0:
    new_in_counterparty_ratio_7d = 0
else:
    new_in_counterparty_ratio_7d = n_new_in / n_in
```

Equivalent to plan’s `n_new_in / max(n_in_unique_7d, 1)` with the zero-in case short-circuit to `0`.

### 7.6. `new_out_counterparty_ratio_7d`

```text
n_out = |out_set(A)|
n_new_out = |{ cp ∈ out_set(A) | cp ∉ hist_out(A) }|

if n_out == 0:
    new_out_counterparty_ratio_7d = 0
else:
    new_out_counterparty_ratio_7d = n_new_out / n_out
```

### 7.7. `inflow_concentration_7d` (HHI)

Inbound USD weight: `amount_received` on txs with `to_account_key = A` in `W`.

```text
For each source s ∈ in_set(A):
    inflow_s = sum(amount_received of tx in W with to=A and from=s)

total_inflow = sum_s inflow_s

if total_inflow == 0:
    inflow_concentration_7d = 0
else:
    share_s = inflow_s / total_inflow
    inflow_concentration_7d = sum_s (share_s ** 2)
```

Single source → HHI = `1`. Range conceptually `[0, 1]` for finite positive sources.

### 7.8. `outflow_dispersion_7d` (`1 - HHI_out`)

Outbound USD weight: `amount` on txs with `from_account_key = A` in `W`.

```text
For each dest d ∈ out_set(A):
    outflow_d = sum(amount of tx in W with from=A and to=d)

total_outflow = sum_d outflow_d

if total_outflow == 0:
    outflow_dispersion_7d = 0
else:
    share_d = outflow_d / total_outflow
    HHI_out = sum_d (share_d ** 2)
    outflow_dispersion_7d = 1 - HHI_out
```

Single destination → dispersion = `0`.

---

## 8. Cold-start policy

Applies to interpretation of `new_in_counterparty_ratio_7d` and `new_out_counterparty_ratio_7d`.

### 8.1. Metadata columns (required in parquet)

Not part of the “8 core measurements” for model semantics, but **required** on each feature row:

| Column | Type | Definition |
|--------|------|------------|
| `history_available` | int `0`\|`1` | `1` iff `|H| >= 1` (any in or out tx with `occurred_at < start_ts`), else `0` |
| `history_days_observed` | int ≥ 0 | Number of distinct UTC calendar dates `date(occurred_at)` among txs in `H`; `0` if `H` empty |

### 8.2. Interpretation rules

- Formulas for `new_*` **unchanged** when cold-start (may be `1.0` with empty history).
- **Do not** treat `new_* = 1` with `history_available = 0` as strong AML / structural-expansion evidence.
- Agent / reports / later detectors that consume these columns should gate on `history_available == 1` (optional stricter gate on `history_days_observed` is **open** — not invented here; default gate = `history_available` only).

---

## 9. Output schema — `graph_features_v1.parquet`

**Path:** `data/processed/graph_features_v1.parquet`
**One row = one sample** `(account_key, as_of_ts, window="7d")` that passes §3.2.

| Column | Dtype (logical) | Required | Notes |
|--------|-----------------|----------|-------|
| `account_key` | string | yes | |
| `as_of_ts` | timestamptz UTC | yes | `= end_ts` |
| `snapshot_date` | date UTC | yes | `D` |
| `window` | string | yes | `"7d"` |
| `sample_split` | string | yes | `train`\|`val`\|`test` |
| `feature_schema_version` | string | yes | `"graph_features_v1"` |
| `in_degree_7d` | int | yes | |
| `out_degree_7d` | int | yes | |
| `unique_neighbors_7d` | int | yes | |
| `in_out_degree_ratio_7d` | float | yes | |
| `new_in_counterparty_ratio_7d` | float | yes | |
| `new_out_counterparty_ratio_7d` | float | yes | |
| `inflow_concentration_7d` | float | yes | |
| `outflow_dispersion_7d` | float | yes | |
| `history_available` | int | yes | `0`\|`1` |
| `history_days_observed` | int | yes | |

**Primary key:** `(account_key, as_of_ts, window)`.

**Sorting (recommended for determinism):** `as_of_ts`, `account_key`.

**Non-goals for this file:** `detection_id`, `pattern_instance_id`, `graph_score`, detector columns.

---

## 10. Anti-leakage checklist (features)

- [ ] No `label_*` in feature columns (`assert_no_label_leakage` on output column list excluding metadata if needed — at least assert no column starts with `label_`).
- [ ] No transaction with `occurred_at >= as_of_ts` used in any feature or cold-start field.
- [ ] History for `new_*` uses only `occurred_at < start_ts`.
- [ ] `sample_split` from `assign_snapshot_split` only.

---

## 11. Unit tests required (before / with feature implementation)

| Test | Expectation |
|------|-------------|
| Window bounds | Tx at `occurred_at == end_ts` **excluded**; tx at `start_ts` **included** |
| Future leak | Injecting tx with `occurred_at >= end_ts` does not change features |
| In/out degree | Fixture fan-in / fan-out → correct unique counts |
| Unique neighbors | Neighbor in both directions counted once |
| Ratio both zero | `in=0,out=0` → `in_out_degree_ratio_7d == 0` |
| New-in ratio | Known hist vs window CP → exact fraction |
| New-out ratio | Symmetric |
| HHI single source | `inflow_concentration_7d == 1.0` |
| Dispersion single dest | `outflow_dispersion_7d == 0.0` |
| Zero flow | No inbound → concentration `0`; no outbound → dispersion `0` |
| Cold-start | No history → `history_available==0`, `history_days_observed==0`, `new_*` may be 1 if degree>0 |
| With history | `history_available==1`; `new_*` excludes hist CPs |
| `assign_snapshot_split` | Boundaries vs fixture cutoffs: `as_of_ts == train_end` → train; just after → val; after `val_end` → test |
| Sample eligibility | Account with no in-window tx → **no row** |
| Label leak | Output columns have no `label_` prefix |
| Determinism | Same input DB + cutoffs → identical parquet (or identical checksum of sorted rows) |

Detectors / CYCLE / FAN — **out of scope** for these tests.

---

## 12. Implementation notes (non-normative)

- Prefer DuckDB window aggregates / group-bys before pulling full graphs into Python.
- Shared helper `assign_snapshot_split` must be imported by Graph and IF — do not copy-paste divergent versions.
- `feature_schema_version` bumps only when formulas/columns change incompatibly.

---

## 13. Out of scope (do not implement under this spec)

- CYCLE / FAN_IN / FAN_OUT / GATHER_SCATTER detectors
- `graph_detection_v1.parquet` / `graph_evidence_v1.jsonl`
- `graph_score`
- FAN/GATHER threshold values
- GT matching to IBM pattern instances
- PageRank / betweenness / GNN / extra features beyond §7–§8

---

*Spec v1.0 — derived from `docs/graph_branch_plan.md` v0.5. Detectors intentionally omitted.*
