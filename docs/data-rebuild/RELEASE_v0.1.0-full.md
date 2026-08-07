# ABM-BANK-v0.1.0-full

The complete canonical CSV release: **every IBM account, every transaction,
every laundering pattern**. Built from `HI-Medium_Trans.csv`
(sha256 `3126afb8…`, 31,898,238 rows) plus its accounts and patterns companions,
joined to Vietnamese statistics acquired from the World Bank API.

```bash
python -m abm.cli build-release --mode full --version 0.1.0-full
python -m abm.cli validate-release --release data/releases/ABM-BANK-v0.1.0-full
python -m abm.cli compare-ibm      --release data/releases/ABM-BANK-v0.1.0-full
```

Build time ≈ 25 minutes, peak memory ≈ 9 GB, output 6.8 GB.

## Why the small release was replaced

The earlier 6,000-account slice covered **1.4%** of IBM and was biased by
construction: an activity band of 5–1,000 transactions excluded the 33% of
accounts with three or fewer, and one-hop expansion from laundering seeds
preferred well-connected accounts. Measured against IBM, its median account made
**68 transactions against IBM's 7** — a 9.67× deviation.

`full` drops the band, the seeding, and the expansion. Every account is internal,
so every edge is internal and there is almost no external boundary.

| | small | **full** |
|---|---:|---:|
| Accounts | 6,000 | **2,077,023** |
| Transactions | 461,537 | **31,901,650** |
| IBM coverage | 1.4% | **99.99%** |
| Internal-to-internal events | 22.4% | **92.0%** |
| Laundering transactions | 4,194 | **35,230** (all of IBM's) |
| Scenario instances | 150 | **493** (all of IBM's) |
| KYC max marginal error | 0.0162 | **0.0006** |

## Row counts and checksums

| File | Rows | MB | SHA-256 (16) |
|---|---:|---:|---|
| `bank_view/customers.csv` | 1,827,781 | 267.3 | `0e47403d0346aef7` |
| `bank_view/businesses.csv` | 249,242 | 30.3 | `7d6d4e5bc22f0148` |
| `bank_view/accounts.csv` | 2,077,023 | 177.7 | `a659f8d7e91377a2` |
| `bank_view/transactions.csv` | 31,901,650 | 4841.5 | `7ba85cb1b59b89ba` |
| `bank_view/devices.csv` | 1,788,611 | 144.6 | `301bc7ec44aba5da` |
| `bank_view/merchants.csv` | 116,146 | 4.8 | `e07cacc7fc031926` |
| `bank_view/relationships.csv` | 4,340,688 | 356.6 | `8cd3fefd86273a09` |
| `ground_truth/entity_labels.csv` | 2,118,880 | 208.2 | `62c0e8337322d43a` |
| `ground_truth/transaction_labels.csv` | 31,901,650 | 882.4 | `f5316cae5f9dad1b` |
| `ground_truth/scenario_instances.csv` | 493 | 0.1 | `d7f6af89a01dc5b5` |
| `ground_truth/criminal_networks.csv` | 4,748 | 0.4 | `c7f3c47eec11167f` |
| `ground_truth/hard_negative_instances.csv` | 225 | 0.0 | `354ab6da8b63fcbd` |
| `splits/train_entities.csv` | 1,453,362 | 38.8 | `36e1744b3c5ae5f8` |
| `splits/validation_entities.csv` | 208,091 | 6.5 | `2f17eac88a525b47` |
| `splits/test_entities.csv` | 207,477 | 5.3 | `09ab90ae3c7048c3` |
| `splits/hidden_test_entities.csv` | 208,093 | 6.7 | `03b659f52deeb96a` |

All 20 files, including reports, are checksummed in `manifest.json`.

## Validation — 7 PASS, 1 WARN

| Gate | Verdict |
|---|---|
| Schema and data quality | PASS |
| Primary keys | PASS |
| Foreign keys | PASS |
| Temporal | PASS |
| Monetary | PASS |
| Graph | PASS |
| Splits | PASS |
| **Leakage** | **WARN** — see below |

### Graph

| | |
|---|---:|
| Nodes | 1,765,228 |
| — internal accounts | 1,758,298 |
| — external counterparties | 6,930 |
| Unique edges | 3,005,637 |
| Transaction events | 31,901,650 |
| **Internal-to-internal events** | **29,334,558 (92.0%)** |
| Self-loop events | 2,560,162 |
| Reciprocal edges | 65,956 |
| Connected components | 63,402 |
| Largest component | 1,615,786 (91.5%) |
| Degree median / p95 / max | 12 / 116 / 1,083,821 |

The 1,083,821-degree node is IBM's correspondent hub, preserved rather than
excluded — in the full release it is the clearing bank it always was.

### Splits

| Split | Entities | Share |
|---|---:|---:|
| TRAIN | 1,453,362 | 69.97% |
| VALIDATION | 208,091 | 10.02% |
| TEST | 207,477 | 9.99% |
| HIDDEN_TEST | 208,093 | 10.02% |

**493 criminal networks checked, 0 spanning a split.**

### Monetary

Median 40,648 ₫ · p75 248,499 ₫ · p95 5,946,709 ₫ · p99 28,379,131 ₫.
0.04% of amounts exceed 1 billion ₫; 8.98% fall below 1,000 ₫. Both tails are
inherited from IBM's within-account spread, which calibration preserves by
design, and are reported rather than clipped.

### Leakage — WARN, and why it is not a failure

**0 perfect predictors. Mutual information ≤ 0.00046 bits on every attribute.**

Four attribute values exceed the 3× lift threshold, all of them the very largest
businesses:

| Attribute | Value | Entities | Flagged | Lift |
|---|---|---:|---:|---:|
| `revenue_band` | 5B-20B | 49 | 7 | 7.09× |
| `employee_size_band` | 200+ | 35 | 4 | 5.67× |
| `domestic_international_profile` | INTERNATIONAL_HEAVY | 62 | 5 | 4.00× |
| `revenue_band` | 1B-5B | 293 | 18 | 3.05× |

Base rate 2.02% (41,857 of 2,077,023).

**The mechanism.** Rank matching maps firm size to expected turnover, and the
highest-turnover IBM accounts are more often laundering-involved because
laundering patterns move value through hub-like accounts. So the largest
businesses land on the busiest accounts.

**Why it is reported rather than engineered away.** The four cells hold 439
entities in total — 0.02% of the population — and mutual information is
effectively zero, so no model can exploit the association at any useful scale.
It is also arguably *correct*: large, internationally exposed firms genuinely do
carry higher AML risk, which is why banks apply enhanced due diligence to them. A
dataset in which firm size were uncorrelated with AML involvement would be less
realistic, not more.

The small release did not surface this because it contained too few large
businesses for any cell to reach the minimum size. **The WARN is the gate
working.**

## Quality against raw IBM

Four things are changed on purpose and are therefore not comparable: absolute
amounts (rescaled to VND), payment format (IBM's predicted its own label at 7.2×
lift), time of day (IBM's is uniform random), and identifiers.

Everything else is claimed to survive, and that is what is measured.

| | IBM | Release |
|---|---:|---:|
| Transactions | 31,898,238 | 31,894,720 from IBM + 6,930 simulated |
| **Coverage** | — | **99.989%** |
| Accounts | 2,077,023 | 2,077,023 |
| **Self-transfer share** | **8.0314%** | **8.0252%** |
| Laundering transactions | 35,230 | 35,230 |
| Laundering rate | 0.1104% | 0.1104% |

The 3,518 dropped transactions (0.011%) belong to accounts with no observed
inflow, which cannot be assigned a calibration scale. They carry an explicit
reason rather than a substituted default.

### Per-account structure — PASS, worst deviation 0.6%

Recomputed from the shipped CSV, not from builder state, so it measures what a
consumer would actually see.

| Feature | IBM p50 | Release p50 | IBM p95 | Release p95 | Worst dev |
|---|---:|---:|---:|---:|---:|
| `transaction_count` | 7 | 7 | 114 | 114 | **0.000** |
| `fan_in_ratio` | 0.040 | 0.040 | 0.667 | 0.667 | 0.001 |
| `fan_out_ratio` | 0.065 | 0.066 | 1.000 | 1.000 | 0.006 |
| `flow_balance` | 0.000 | 0.000 | 0.957 | 0.957 | 0.006 |
| `unique_inbound_counterparties` | 1 | 1 | 4 | 4 | 0.002 |
| `unique_outbound_counterparties` | 1 | 1 | 5 | 5 | 0.001 |

Populations: 2,077,023 IBM accounts against 2,076,129 active in the release.

**A correction worth recording.** The first run of this comparison reported all
six features outside tolerance, with the release median at 12 transactions
against IBM's 7. That was a defect in the comparison tool, not the data: it
skipped self-transfers entirely, which dropped every account whose only activity
is internal and computed the release median over a strictly busier
subpopulation. IBM's own profiler counts a self-transfer toward volume but not
toward counterparties, and once the comparison did the same the deviation fell
from 71% to 0%.

**Typology coverage — all 493 instances, matching IBM's own distribution
exactly:** FAN-OUT 74 · STACK 70 · CYCLE 67 · SCATTER-GATHER 65 · FAN-IN 62 ·
BIPARTITE 57 · RANDOM 53 · GATHER-SCATTER 45.

## Distribution against Vietnamese sources

**PASS, max absolute error 0.000637** — a 25× improvement on the small release,
because 1.83 million customers leaves almost no sampling noise.

| Attribute | Source | Generated | Error |
|---|---:|---:|---:|
| `has_formal_borrowing` | 0.4320 | 0.4326 | 0.0006 |
| `income_band` Q3 | 0.2000 | 0.1995 | 0.0005 |
| `age_band` 25-34 | 0.1867 | 0.1863 | 0.0004 |
| `has_mobile_money` | 0.3872 | 0.3868 | 0.0004 |
| `uses_digital_payment` | 0.6238 | 0.6234 | 0.0004 |

Every other check is below 0.0004.

## Known limitations

12 recorded in `manifest.json`, unchanged from the small release in substance.
The binding ones:

1. **IBM is 99.7% businesses** (3,017 individual accounts in 2.08 million).
   Synthetic retail customers are matched to business behavior. Largest bias.
2. **27.67-day window.** No monthly seasonality, no 30/60/90-day baselines.
3. **Splits are by entity and network, not time.** Transactions carry a
   `time_partition` marker instead.
4. **Payment format and time of day are assumption-driven**, replacing IBM
   columns that were unusable.
5. **The 2.02% entity flag rate is not a prevalence estimate.**
   `prevalence_claim: false`. The transaction-level rate, 0.1104%, is IBM's.
6. No sub-national region; age independent of employment and income; firm size
   assumed Pareto; the income-to-turnover multiple unevidenced; one account per
   entity; internal edges use the geometric mean of two scale factors.

29 assumptions are registered in `manifest.json` with values and sensitivity
ranges.

## Consumption

Both tracks read the same Bank View. Ground Truth is joined only after features
are computed.

- **Hường** — `customers`, `accounts`, `transactions`, `devices`, `merchants`
- **Hiển** — the above plus `relationships`

At this scale `transactions.csv` is 4.8 GB; read it in chunks or convert to
Parquet in your own workstream directory. Do not modify the release.
