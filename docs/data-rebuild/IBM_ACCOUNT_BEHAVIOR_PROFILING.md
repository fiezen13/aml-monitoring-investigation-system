# IBM account behavior profiling

Phase 2 of the data rebuild: describe what every IBM account *does*, so that
Phase 3 can derive archetypes from evidence and Phase 9 can match synthetic
Vietnamese KYC agents onto real behavioral patterns.

Artifacts (both gitignored):

- `artifacts/intermediate/ibm_account_behavior_profiles.csv` — 2,077,023 rows, 470 MB
- `artifacts/source_profiles/ibm_account_behavior_summary.json` — distributions

Reproduce with:

```bash
python -m abm.cli profile-ibm-behavior \
    --input    data/raw/ibm-aml/HI-Medium_Trans.csv \
    --accounts data/raw/ibm-aml/HI-Medium_accounts.csv
```

One pass over 31,898,238 transactions; peak resident memory about 17 GB.

## 1. The rule that shaped the implementation

**The laundering label is never read.** `is_laundering` is dropped at the column
level in `abm/profiling/ibm_behavior.py` before any feature is computed —
`FORBIDDEN_COLUMNS` — and the summary records `is_laundering_read: false`.

This is not a formality. If normal-customer archetypes were derived with the
label in scope, the archetypes would encode the answer, KYC profiles matched
through them would inherit it, and every model trained on the result would be
measuring its own leakage. Archetypes must be derivable by a bank that has never
seen a label.

## 2. Account identity

Identity is `normalized_bank:account_number`, with leading zeros stripped from
the bank. The transaction file writes the same bank as both `020` and `0020`
(Finding I1); the accounts file stores it as `20`. Without normalization the
join to entity data silently fails for a subset of accounts.

Self-transfers — 8.03% of all rows, essentially every `Reinvestment` — are
excluded from counterparty counts and reported in their own column. They are an
account paying itself, not an edge.

## 3. Schema

44 columns per account. Counts and sums are exact; medians are PyArrow's
`approximate_median`.

| Group | Columns |
|---|---|
| Identity | `account_key`, `entity_id`, `entity_kind` |
| Volume | `transaction_count`, `incoming_transaction_count`, `outgoing_transaction_count`, `self_transfer_count` |
| Value | `total_incoming_amount`, `total_outgoing_amount`, `mean_*`, `median_*`, `max_transaction_amount`, `net_flow_amount`, `turnover_amount` |
| Counterparties | `unique_inbound_counterparties`, `unique_outbound_counterparties`, `fan_in_ratio`, `fan_out_ratio`, `counterparty_diversity` |
| Time | `active_days`, `first_active_day_index`, `last_active_day_index`, `observed_span_days`, `activity_density`, `transactions_per_active_day`, `transactions_per_observed_day` |
| Balance of flow | `incoming_outgoing_count_ratio`, `incoming_outgoing_amount_ratio` |
| Rhythm | `night_transaction_share`, `weekend_transaction_share` |
| Instrument | `distinct_currencies`, `distinct_payment_formats`, `dominant_currency`(+share), `dominant_payment_format`(+share) |
| Shape flags | `possible_salary_like_pattern`, `possible_business_like_pattern`, `possible_high_turnover_pattern`, `possible_low_frequency_pattern` |

`fan_in_ratio` is unique inbound counterparties divided by inbound transaction
count: 1.0 means every receipt came from a different party, near 0 means one
party sends repeatedly.

The four shape flags are **not** the archetypes. Their thresholds are arbitrary
and are stated in the code rather than a config precisely because none is
evidence-derived. They exist so a reviewer can confirm the numbers describe
recognizable behavior before any clustering is trusted.

## 4. What the accounts look like

Every one of the 2,077,023 accounts matched an entity in the accounts file. No
unmatched accounts.

| Feature | min | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| `transaction_count` | 1 | 3 | **7** | 42 | 114 | 1,083,821 |
| `active_days` | 1 | 2 | **4** | 16 | 16 | 26 |
| `unique_inbound_counterparties` | 0 | 0 | **1** | 2 | 4 | 2,304 |
| `unique_outbound_counterparties` | 0 | 0 | **1** | 2 | 5 | 55,956 |
| `transactions_per_active_day` | 1.0 | 1.33 | 2.0 | 3.62 | 7.69 | 67,739 |
| `fan_in_ratio` | 0 | 0 | 0.06 | 0.20 | 0.80 | 1.0 |
| `fan_out_ratio` | 0 | 0 | 0.07 | 0.33 | 1.0 | 1.0 |
| `turnover_amount` | 0 | 4,549 | 54,726 | 799,128 | 38.6 M | 13.1 T |

The median account makes 7 transactions across 4 days with one counterparty on
each side. Fan ratios near 0.06 say most accounts transact repeatedly with the
same few parties rather than with many.

Realized flag counts, which are as much a check on the thresholds as on the data:

| Flag | Accounts | Share |
|---|---:|---:|
| `possible_high_turnover_pattern` | 836,563 | 40.28% |
| `possible_low_frequency_pattern` | 695,069 | 33.46% |
| `possible_salary_like_pattern` | 601,110 | 28.94% |
| `possible_business_like_pattern` | 4,141 | **0.20%** |

The business-like flag requires five or more unique counterparties on *both*
sides. Only 0.20% of accounts qualify — because the 95th percentile of unique
counterparties is 4 inbound and 5 outbound (§4). The threshold is not wrong so
much as mis-scaled for a 28-day window, and it is a concrete illustration of why
Phase 3 must derive archetypes from the data rather than assert them: a
hand-picked rule that sounds reasonable captures 0.2% of the population.

## 5. Findings

### B1 — a third of accounts are too sparse to profile

| Transactions | Accounts | Share |
|---|---:|---:|
| 1 | 69,438 | 3.34% |
| 2–3 | 625,631 | 30.12% |
| 4–9 | 433,889 | 20.89% |
| 10–29 | 234,643 | 11.30% |
| 30–99 | 572,807 | 27.58% |
| 100–999 | 140,600 | 6.77% |
| 1,000+ | 15 | 0.00% |

33.5% of accounts have three transactions or fewer. A median, a fan ratio, and
an inter-arrival estimate computed on three events are noise.

This is not a blocker for the small release. Accounts with at least 10
transactions number **948,065 (45.7%)**, and at least 30 gives **713,422
(34.4%)** — abundant against a target of roughly 5,000 customers. Phase 3 should
derive archetypes on the ≥10 pool and record the minimum as a registered
parameter, rather than clustering two million accounts of which a third carry no
signal.

### B2 — the time signal is largely absent

Hour-of-day across all 31.9 million transactions:

| Hour | Share | | Hour | Share |
|---|---:|---|---|---:|
| 00:00 | **10.57%** | | 12:00 | 3.89% |
| 01:00–11:00 | 3.88–3.90% each | | 13:00–23:00 | 3.88–3.90% each |

**Every hour from 01:00 to 23:00 holds 3.88–3.90% of transactions.** A uniform
distribution would be 4.17%. The 10.57% at midnight is a rounding artifact of
timestamps that default to 00:00.

IBM's simulator assigns times uniformly at random. There is no business day, no
overnight lull, no lunch peak.

Day-of-week is skewed, over exactly four complete weeks (2022-09-01 Thursday
through 2022-09-28 Wednesday, each weekday appearing exactly four times):

| Day | Share | | Day | Share |
|---|---:|---|---|---:|
| Mon | 12.10% | | Fri | **27.16%** |
| Tue | 12.10% | | Sat | 5.21% |
| Wed | 12.11% | | Sun | 5.21% |
| Thu | **26.11%** | | | |

Thursday and Friday carry 53% of all activity; weekends carry 10.4%.

The consequence for Hường's feature set is direct: **night-activity share,
business-hours deviation, and unusual-hour flags are standard AML behavioral
features, and computed on IBM timestamps they are pure noise.** The median
account's `night_transaction_share` of 0.40 is what uniform randomness produces
across an 8-hour window, not evidence of nocturnal behavior.

Either timestamps are re-drawn through a Vietnamese diurnal model during Phase
11, or the temporal feature family is declared unsupported for v0.1.0. The first
option costs the exact inter-arrival structure IBM provides; the second costs a
feature family. This needs a decision and is `UNRESOLVED_TEMPORAL_REALISM`.

### B3 — the individual population is unusable, confirmed at behavior level

| Entity kind | Accounts | Median tx | Mean tx |
|---|---:|---:|---:|
| Partnership | 728,793 | 7.0 | 29.5 |
| Corporation | 676,517 | 6.5 | 27.7 |
| Sole Proprietorship | 663,931 | 8.6 | 35.1 |
| Country | 4,738 | — | — |
| **Individual** | **3,017** | **5.0** | **14.1** |
| Direct | 27 | — | — |

Individual accounts are 0.15% of the population and are *less* active than
business accounts. Phase 9 wants to match roughly 5,000 synthetic Vietnamese
retail customers onto individual behavior; the entire pool of individual
accounts with 10 or more transactions is a few hundred.

Matching retail customers onto Corporation or Partnership behavior would give
Vietnamese individuals the transaction patterns of businesses. This is
`UNRESOLVED_INDIVIDUAL_BEHAVIOR` and it is the finding most likely to change the
architecture.

### B4 — dominant payment format is concentrated

| Dominant format | Accounts | Share |
|---|---:|---:|
| Cheque | 830,645 | 39.99% |
| Reinvestment | 607,448 | 29.25% |
| Credit Card | 283,638 | 13.66% |
| ACH | 266,644 | 12.84% |
| Bitcoin | 42,046 | 2.02% |
| Cash | 41,158 | 1.98% |
| Wire | 5,444 | 0.26% |

29% of accounts do mostly self-payment (`Reinvestment`). Combined with Finding
L1 — ACH carries 7.2× the laundering rate, Wire and Reinvestment carry none —
this column cannot be carried into Bank View unchanged.

## 6. Readiness for Phase 3

**Ready.** The feature frame is label-free, covers 2.08 million accounts, and
has a usable high-activity subset of 948,065.

Two prerequisites before clustering:

1. **Add `numpy` and `scikit-learn`.** Neither is installed; the environment has
   only `pyarrow` and `PyYAML`. K-means, GMM, and silhouette scoring need them.
   Quantile segmentation alone would work without new dependencies but cannot
   demonstrate the cluster stability Phase 3 asks for.
2. **Decide the minimum-activity threshold**, and register it as a parameter card
   rather than a constant in code.

Recommended feature set for clustering — scale-free, so a hub and a retail
account can share an archetype if they behave alike:
`transactions_per_active_day`, `activity_density`, `fan_in_ratio`,
`fan_out_ratio`, `incoming_outgoing_count_ratio`,
`log(turnover / median_transaction)`, `self_transfer_count / transaction_count`,
`dominant_payment_format_share`, `distinct_currencies`.

Deliberately excluded: absolute amounts, since IBM mixes fifteen currencies
across eighteen orders of magnitude and the scale carries no Vietnamese meaning;
and `night_transaction_share` and `weekend_transaction_share`, per Finding B2.
