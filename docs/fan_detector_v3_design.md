# FAN Detector v3 Design — FIN-07

**Status:** **CLOSED — v3-min frozen and final test run once (2026-08-11); do not retune.**
**Scope:** FAN_IN and FAN_OUT only. Test remains final evaluation only.

## 1. Evidence for redesign

Train-only temporal backtest shows:

- v2B absolute degree/shape gates have zero FAN_IN recall in both early and late train cohorts.
- A softer `degree >= 8` plus `HHI <= 0.30` rule is stable but reaches only 50% recall in each cohort.
- Relaxing enough to include low-degree/high-HHI FAN patterns causes unacceptable account-snapshot volume.
- FAN_OUT train/val Pareto has the same issue: balanced recall remains low below a 1% validation alert budget.

Therefore v3 must distinguish suspicious **activity dynamics** from benign high-degree hubs. Higher or lower absolute degree thresholds alone are not v3.

## 2. Detection unit and leakage contract

Keep `(account_key, as_of_ts, window="7d")`, half-open window, sample split, IDs, and transaction evidence contracts unchanged.

- Feature/calibration data: train only.
- Model/rule selection: validation; for FAN_IN, use train-internal temporal folds until validation contains no GT.
- Test: one final evaluation after v3 is frozen.
- IBM labels are evaluation/tuning targets only, never detector inputs.

## 3. v3 measurements

### Core structural measurements

- `in/out_degree_7d`
- `in/out_tx_count_7d`
- `tx_per_counterparty_7d = tx_count / max(degree, 1)`
- inbound HHI / outbound dispersion retained as soft signals, not mandatory gates

### Temporal burst measurements

- `max_tx_count_24h / tx_count_7d`
- `max_unique_counterparties_24h / degree_7d`
- `active_span_hours` between first and last directional transaction
- optional 6-hour equivalents, retained only if train-fold stability improves

### Network-change measurements

- `new_counterparty_count_7d` and `new_counterparty_ratio_7d`
- degree/tx-count acceleration versus the immediately preceding 7-day window
- novelty is available only when `history_available=1` and a minimum observed-history policy is met

Novelty must never be mandatory when history is unavailable. Current train FAN_IN GT occurs near dataset start, so the present data cannot establish novelty effectiveness for those instances.

## 4. Detector structure

### Stage A — broad candidate generation

Use a low structural floor on directional degree and transaction count to remove one-off activity. Exact floors must be chosen inside train folds; they must not be inferred from test GT.

### Stage B — missing-aware interpretable score

Convert each measurement to an empirical percentile learned from train account-snapshots. Suggested signal groups:

1. structural intensity: degree and transaction count;
2. temporal concentration: 24-hour counterparty/transaction burst;
3. network change: novelty and acceleration;
4. money-flow shape: HHI/dispersion.

Combine group scores using a documented point system or monotonic model. Normalize by the weights of available groups so cold-start novelty is absent rather than treated as zero risk. Emit group contributions in evidence.

Do not freeze weights yet: six FAN_IN train instances and two FAN_OUT validation instances are insufficient for unconstrained supervised fitting.

## 5. Selection protocol

1. Materialize proposed measurements for train/val only.
2. Use strict temporal folds inside train; report each fold separately.
3. Select candidates under explicit alert budgets (0.25%, 0.5%, 1%, and episode-level analyst capacity).
4. Require recall stability across folds, not only aggregate recall.
5. Validate FAN_OUT on existing validation GT. FAN_IN remains provisionally selected by temporal train backtest because validation has zero GT.
6. Freeze schema, thresholds/weights, evidence version, and config hash.
7. Run test exactly once for final evaluation.

## 6. Acceptance criteria before test

- No temporal fold with zero recall when that fold contains GT.
- Material improvement over degree+shape at the same account-snapshot alert rate.
- Results reported both per snapshot and after consecutive alerts are merged into episodes.
- Every alert retains transaction-level evidence and per-signal explanation.
- Cold-start and missing-history behavior tested explicitly.

If v3 cannot improve train-fold/validation Pareto at fixed alert volume, the new measurements are rejected rather than carried into test.

## 7. Frozen implementation and final test

Frozen config: `configs/graph/graph_fan_config_v3.json`. It was selected using train temporal backtest and validation alert volume only. The final test comparison is recorded in `reports/fan_final_test_comparison_v1.json`; config SHA-256 is stored in that report.

| Version | FAN_IN recall / predictions / alert rate | FAN_OUT recall / predictions / alert rate |
|---|---|---|
| v1 | 33.3% / 11,275 / 0.264% | 50.0% / 7,075 / 0.165% |
| v2B | 0.0% / 6,625 / 0.155% | 30.0% / 2,549 / 0.060% |
| v3-min | **50.0% / 32,176 / 0.752%** | **80.0% / 23,363 / 0.546%** |

No serious schema, ID, split, or matching bug was found. FAN is closed without post-test threshold changes.

### Limitations

- Ground truth is extremely small: six FAN_IN and ten FAN_OUT test instances.
- IBM GT may be incomplete, so unmatched predictions are proxy false positives rather than confirmed false positives.
- v3-min improves recall but materially increases alert volume; its precision against known IBM instances remains very low.
- FAN_IN had no validation GT, so its pre-test selection relied on train-only temporal cohorts plus validation alert volume.
- The UTC-day concentration measurement reflects temporal spread in this dataset; it is not proof of an AML burst and may not transfer to other datasets.
- No further threshold tuning is allowed from these test results. Any future change must be a separately versioned detector evaluated under a new pre-registered protocol.
