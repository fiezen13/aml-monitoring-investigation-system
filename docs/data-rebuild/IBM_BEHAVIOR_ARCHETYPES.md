# IBM behavioral archetypes

Phase 3. Five archetypes derived from 947,138 IBM accounts, without the
laundering label.

```bash
python -m abm.cli derive-archetypes
```

Artifacts (gitignored): `artifacts/intermediate/ibm_account_archetypes.csv`,
`artifacts/source_profiles/ibm_archetypes.json`,
`artifacts/source_profiles/ibm_archetype_leakage.json`.

## Population

| | Accounts |
|---|---:|
| In the behavior profile | 2,077,023 |
| Excluded, under 10 transactions | 1,129,885 |
| Excluded, no usable typical transaction size | 927 |
| **Clustered** | **947,138** |

The 10-transaction floor is not a convenience. Below it a median, a fan ratio,
and an inter-arrival estimate are all computed from three or four events, and
clustering them produces clusters of noise that outnumber the real segments.

## Features

Ten scale-free features. Nothing absolute, because IBM mixes fifteen currencies
across eighteen orders of magnitude and Phase 8 rescales the money anyway.

| Feature | What it captures |
|---|---|
| `log_transactions_per_active_day` | Burstiness on days the account is active |
| `activity_density` | Share of its own lifespan the account is active |
| `fan_in_ratio` / `fan_out_ratio` | Distinct counterparties per transaction |
| `flow_direction_balance` | (in − out) / (in + out) by count |
| `value_direction_balance` | The same by amount; near zero means pass-through |
| `log_turnover_multiple` | Turnover over a typical single payment |
| `self_transfer_share` | Share sent to itself |
| `dominant_format_share` | Instrument concentration — not which instrument |
| `log_distinct_currencies` | Currency spread |

Direction is expressed as `(a − b) / (a + b)` rather than `a / b`. The quotient
is undefined for an account that only receives and explodes for one that almost
only receives; the contrast is defined everywhere on [−1, 1].

**Three exclusions, each on evidence:**

- **Absolute amounts** — no comparable meaning across fifteen currencies.
- **Time of day and weekday** — IBM assigns times uniformly at random
  (Finding B2). Clustering on noise manufactures clusters.
- **Which payment format** — it predicts the label at 7.2× lift (Finding L1).
  Only its *concentration* is used, which is a behavioral trait rather than an
  instrument identity.

## Choosing k

Silhouette on a 150,000-account subsample, with Davies-Bouldin and
Calinski-Harabasz alongside so the choice does not rest on one index.

| k | Silhouette ↑ | Davies-Bouldin ↓ | Calinski-Harabasz ↑ | Smallest cluster |
|---:|---:|---:|---:|---:|
| 3 | 0.2147 | 1.670 | 30,917 | 17.0% |
| 4 | 0.2483 | 1.423 | 32,432 | 6.7% |
| **5** | **0.2659** | **1.256** | **35,564** | 4.0% |
| 6 | 0.2556 | 1.276 | 33,620 | 4.0% |
| 7 | 0.2591 | 1.237 | 32,437 | 4.0% |
| 8 | 0.2428 | 1.306 | 31,231 | 4.0% |
| 12 | 0.2375 | 1.296 | 27,823 | 1.8% |

All three indices agree on k = 5.

A silhouette of 0.27 is modest and worth saying plainly: **these clusters are
reproducible and interpretable, not well separated.** Behavioral data rarely
separates cleanly, and a claim of clean separation here would be false.

## Stability

| Test | Result |
|---|---|
| Same points, five different seeds | ARI 0.9991 – 0.9999 |
| **Disjoint subsamples, common holdout** | **ARI 0.9984** |

The second is the strict test — two models fitted on halves that share no
accounts, compared on data neither saw. At 0.998 the partition is a property of
the data, not of one sample.

## The five archetypes

Names are composed from whichever features are most distant from the population
mean, using the strongest feature from each of the two leading families. The
candidate names in the project brief — SALARIED_DIGITAL, CASH_HEAVY — were
examples, and none survived contact with the data.

### `INBOUND` — 440,441 accounts (46.5%)

Flow +0.82 sd. Receives almost exclusively (raw balance +0.90), from the same
few senders repeatedly (fan-in 0.06), and rarely pays anyone. Median 40
transactions. The largest archetype by far: IBM's world is full of accounts that
collect.

### `OUTBOUND_BURSTY` — 324,836 accounts (34.3%)

Flow −0.80 sd, burstiness +0.69 sd. Active every day of its life, 5.6
transactions per active day, turnover about 157× a typical payment, repeat
counterparties. Median 83 transactions — the busiest of the common archetypes.

### `SPORADIC_SELF_CYCLING` — 88,464 accounts (9.3%)

Activity density −2.50 sd, the single most extreme value in the whole solution.
Active on 31% of its own lifespan against a population near 90%, with 10% of
activity sent to itself. Median 12 transactions.

### `WIDE_FAN_IN_SINGLE_INSTRUMENT` — 55,427 accounts (5.9%)

Fan-in +3.14 sd — every receipt from a different party — with 83% of activity on
one payment instrument and a net outbound flow. Receives widely, pays narrowly,
on one rail. Structurally this is the collection-and-forward shape, which makes
its label rate below (0.32× lift) worth noting.

### `MULTI_CURRENCY_SELF_CYCLING` — 37,970 accounts (4.0%)

Distinct currencies +4.81 sd, the most extreme feature in the solution. Two
currencies where almost every other account uses one, plus 8% self-transfers and
high burstiness. Median 90 transactions.

## Label association, measured afterwards

Archetypes were derived without the label. This check reads it afterwards and
measures association only — the order is what makes it a validation rather than
leakage. An account counts as flagged if either endpoint of any laundering
transaction touches it.

Base rate among clustered accounts: **3.29%** (41,857 flagged accounts in the source).

| Archetype | Flagged rate | Lift |
|---|---:|---:|
| **MULTI_CURRENCY_SELF_CYCLING** | **21.93%** | **6.67×** |
| SPORADIC_SELF_CYCLING | 4.95% | 1.51× |
| OUTBOUND_BURSTY | 2.82% | 0.86× |
| INBOUND | 1.97% | 0.60× |
| WIDE_FAN_IN_SINGLE_INSTRUMENT | 1.06% | 0.32× |

> **WARN.** One archetype concentrates the label at 6.67×. Nearly a quarter of
> `MULTI_CURRENCY_SELF_CYCLING` accounts are laundering-involved.
>
> The cause is visible in `HI-Medium_Patterns.txt`: IBM's CYCLE typology moves
> value through a chain of currency conversions — one instance in the file runs
> Yuan → USD → Euro → Yuan → Euro → Yuan → USD → USD → Euro → Yen. Currency
> spread is therefore partly a signature of IBM's injector rather than a
> behavioral trait, and `log_distinct_currencies` is a partly leaky feature.
>
> The archetype is kept, because dropping it would remove the currency-hopping
> behavior that makes the dataset interesting for graph work. Instead the matcher
> keeps archetype assignment soft, and the residual association with KYC
> attributes is measured after matching — where it comes out at 1.42× maximum,
> below the 3× threshold.

## What a reviewer should push back on

- The 10-transaction floor is a judgement. It discards 54% of accounts.
- Silhouette 0.27 means the boundaries are soft. An account near a boundary could
  reasonably belong to either side.
- Naming thresholds (0.5 sd to be "distinctive", two families per name) are
  presentational, not statistical.
- `log_distinct_currencies` is partly a label signature. It stays because it is
  also genuinely behavioral, but that is a defensible choice rather than an
  obvious one.
