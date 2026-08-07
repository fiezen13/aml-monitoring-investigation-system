# IBM AML dataset profile

Phase 1 of the data rebuild. Everything below was measured by reading the file,
not taken from its documentation.

Machine-readable profile: `artifacts/source_profiles/ibm_aml_profile.json`
Reproduce with:

```bash
python -m abm.cli profile-ibm --input data/raw/ibm-aml/HI-Medium_Trans.csv
```

## 1. Source identity

| Property | Value |
|---|---|
| Filename | `HI-Medium_Trans.csv` |
| Path | `data/raw/ibm-aml/HI-Medium_Trans.csv` |
| Size | 3,031,783,420 bytes (2.82 GiB) |
| SHA-256 | `3126afb8155e7c8815d62bc5370549a7b5ae6bf7dfe872b3cd7813e66a3d7ff5` |
| Rows | 31,898,238 |
| Profiled | 2026-08-07, 39.6 s single streaming pass |

Two companion files ship with it and are also treated as immutable source:

| File | Size | Rows | Content |
|---|---:|---:|---|
| `HI-Medium_accounts.csv` | 145,008,642 B | 2,087,786 | Bank name, bank ID, account number, entity ID, entity name |
| `HI-Medium_Patterns.txt` | 407,882 B | — | 493 labeled laundering typology instances |

The raw files are never modified. The profiler opens them read-only and the
checksum above is what any release manifest must cite.

## 2. Schema

The header declares eleven columns, **two of which are both named `Account`**:

```text
Timestamp,From Bank,Account,To Bank,Account,Amount Received,Receiving Currency,Amount Paid,Payment Currency,Payment Format,Is Laundering
```

Name-based readers mishandle this. `pandas` renames the second to `Account.1`;
`csv.DictReader` keeps one and silently discards the other. Both behaviors are
library-version-dependent and neither is a safe foundation. Columns are
therefore read **by position**, the same contract `src/aml/csvsource.py` already
uses for the Kafka producer.

| # | Source header | Profile name | Type | Nulls | Conversion failures |
|---:|---|---|---|---:|---:|
| 0 | Timestamp | `timestamp` | `timestamp[s]` | 0 | 0 |
| 1 | From Bank | `from_bank` | `string` | 0 | 0 |
| 2 | Account | `from_account` | `string` | 0 | 0 |
| 3 | To Bank | `to_bank` | `string` | 0 | 0 |
| 4 | Account | `to_account` | `string` | 0 | 0 |
| 5 | Amount Received | `amount_received` | `double` | 0 | 0 |
| 6 | Receiving Currency | `receiving_currency` | `string` | 0 | 0 |
| 7 | Amount Paid | `amount_paid` | `double` | 0 | 0 |
| 8 | Payment Currency | `payment_currency` | `string` | 0 | 0 |
| 9 | Payment Format | `payment_format` | `string` | 0 | 0 |
| 10 | Is Laundering | `is_laundering` | `int8` | 0 | 0 |

**The file is clean.** Zero nulls, zero unparseable values, zero malformed rows
across 31.9 million records. No cleaning step is required before profiling.

Identifiers are strings, never numbers. Bank `015768` is not the integer 15768,
and account `8149656B0` is not a number at all.

## 3. Temporal extent

| Property | Value |
|---|---|
| Format | `%Y/%m/%d %H:%M` |
| Resolution | one minute |
| Timezone | none declared; treated as naive |
| First | 2022-09-01 00:00 |
| Last | 2022-09-28 15:58 |
| **Span** | **27.67 days** |

> **Finding T1 — the window is four weeks, not three months.**
> The previous design assumed roughly 90 simulated days, and both the split
> policy and the behavioral feature set were built on that assumption. A 27.67-day
> file cannot support a monthly-seasonality feature, a 90-day rolling baseline, or
> a four-way chronological split with meaningful windows. This is unresolved
> question `UNRESOLVED_OBSERVATION_WINDOW`.

## 4. Identifiers and scale

| Property | Value |
|---|---:|
| Distinct bank strings, as written | 122,394 |
| Distinct account numbers | 2,076,999 |
| Distinct `bank:account` keys | 2,077,023 |
| Account numbers reused across banks | 24 |

Account numbers are very nearly globally unique — only 24 collisions in 2.08
million. Account identity is still defined as `bank:account`, because relying on
an unstated near-uniqueness property is how a silent merge of unrelated accounts
happens later.

> **Finding I1 — bank identifiers are inconsistently zero-padded.**
> The same bank appears as both `020` and `0020`. Over the first three million
> rows, 71,822 distinct raw bank strings collapse to 71,773 once leading zeros are
> stripped. The transaction file's padding is decorative; the accounts file
> stores bank IDs as plain integers, which confirms the integer form is canonical.
> **All joins must normalize the bank identifier by stripping leading zeros.**
> The 122,394 raw-string count above is therefore an overcount of true banks.

The busiest bank, `070`, appears on 2,979,311 transaction legs — an order of
magnitude beyond the next (`012`, at 240,541). It behaves like a clearing or
correspondent hub rather than a retail bank.

## 5. Amounts

Measured on `amount_paid`. Quantiles are approximated from a log₁₀ histogram at
20 bins per decade; counts, sums, and extremes are exact.

| Statistic | Value |
|---|---:|
| Minimum | 0.000001 |
| p25 | ≈ 211 |
| Median | ≈ 1,496 |
| p75 | ≈ 11,885 |
| p95 | ≈ 530,884 |
| p99 | ≈ 10,592,537 |
| Mean | 4,417,551 |
| Maximum | 8,158,609,321,727.61 |

The mean sits near the 98th percentile — the distribution is extremely heavy
tailed and spans eighteen orders of magnitude. Much of that spread is unit
mixing rather than genuine value spread: Bitcoin amounts run to six decimal
places while Yen and Ruble amounts run to trillions. **Any amount statistic
computed without conditioning on currency is meaningless**, which is precisely
why Phase 8 calibrates on within-account ratios rather than absolute values.

485,087 rows (1.52%) have `Amount Paid` different from `Amount Received`; these
correspond almost exactly to the 485,144 cross-currency rows.

## 6. Currencies and payment formats

15 currencies. The top five carry 73% of rows:

| Currency | Rows | Share |
|---|---:|---:|
| US Dollar | 11,688,249 | 36.6% |
| Euro | 7,315,958 | 22.9% |
| Yuan | 2,330,638 | 7.3% |
| Shekel | 1,408,707 | 4.4% |
| Canadian Dollar | 1,078,358 | 3.4% |

Bitcoin appears as a currency (688,914 rows) and as a payment format. **No
Vietnamese Dong.** The currency mix belongs to IBM's synthetic global world and
carries no information about Vietnam.

Seven payment formats:

| Format | Rows | Share |
|---|---:|---:|
| Cheque | 12,280,058 | 38.5% |
| Credit Card | 8,777,816 | 27.5% |
| ACH | 3,868,410 | 12.1% |
| Cash | 3,217,531 | 10.1% |
| Reinvestment | 1,945,611 | 6.1% |
| Wire | 1,119,774 | 3.5% |
| Bitcoin | 689,038 | 2.2% |

Cheque at 38.5% and Credit Card at 27.5% are not a plausible Vietnamese channel
mix. Payment format must be re-mapped through a Vietnamese channel model, not
carried across.

## 7. Structure

| Property | Value |
|---|---:|
| Self-transfers (source key = destination key) | 2,561,860 |
| Self-transfer share | 8.03% |

Every `Reinvestment` row is an account paying itself. These are internal
movements, not counterparty edges, and including them would corrupt every degree
and fan-in/fan-out statistic. The Phase 2 profiler excludes them from
counterparty counts and reports them in their own column.

## 8. The laundering label

| Value | Rows | Share |
|---|---:|---:|
| 0 | 31,863,008 | 99.8896% |
| 1 | 35,230 | 0.1104% |

`HI` means "high illicit"; even so the positive rate is roughly 1 in 900.

> **Finding L1 — payment format is a strong predictor of the label.**

| Format | Rows | Laundering | P(laundering \| format) | Lift vs base |
|---|---:|---:|---:|---:|
| ACH | 3,868,410 | 30,746 | 0.795% | **7.2×** |
| Bitcoin | 689,038 | 244 | 0.035% | 0.3× |
| Cash | 3,217,531 | 666 | 0.021% | 0.2× |
| Cheque | 12,280,058 | 2,220 | 0.018% | 0.2× |
| Credit Card | 8,777,816 | 1,354 | 0.015% | 0.1× |
| **Reinvestment** | 1,945,611 | **0** | **0.000%** | 0.0× |
| **Wire** | 1,119,774 | **0** | **0.000%** | 0.0× |

87.3% of all laundering rows are ACH, against a 12.1% ACH baseline. Two formats
contain no laundering at all. This is an artifact of IBM's injector, which emits
its typology patterns almost entirely over ACH — visible directly in
`HI-Medium_Patterns.txt`, where nearly every pattern transaction is ACH.

The consequence is concrete: **carrying IBM's payment format into Bank View
unchanged hands any model a single categorical feature that does most of the
work, and two values that are perfect negative predictors.** Phase 14 requires
that no single KYC feature perfectly predicts the label; `Reinvestment` and
`Wire` would violate that on the transaction side before KYC is even generated.
Tracked as `UNRESOLVED_PAYMENT_FORMAT_LEAKAGE`.

Per Phase 2 policy, `is_laundering` is excluded from every behavioral feature,
archetype, and matching step. It is preserved only for `ground_truth/`.

## 9. The accounts file — entity structure

`HI-Medium_accounts.csv` is not mentioned in the repository's dataset README but
is the single most useful companion file, because it states which accounts belong
to the same party and what kind of party that is.

```text
Bank Name,Bank ID,Account Number,Entity ID,Entity Name
National Bank of Los Angeles,20,800104D70,2AA20590D80,Partnership #1
```

The join to transactions works once bank padding is normalized: transaction bank
`020` matches accounts `Bank ID` `20`, and account `800104D70` matches exactly.

Entity legal form, taken from the word before `#` in `Entity Name`:

| Legal form | Accounts | Share |
|---|---:|---:|
| Partnership | 732,828 | 35.1% |
| Corporation | 679,329 | 32.5% |
| Sole Proprietorship | 667,814 | 32.0% |
| Country | 4,738 | 0.23% |
| **Individual** | **3,050** | **0.15%** |
| Direct | 27 | 0.001% |

> **Finding E1 — IBM's world is almost entirely businesses.**
> 99.6% of accounts belong to Partnerships, Corporations, or Sole
> Proprietorships. There are 3,050 individual accounts in a population of 2.09
> million.
>
> This directly contradicts the shape of the intended Vietnamese customer
> population, which is mostly individual retail customers. The rebuild's premise
> is that IBM supplies behavioral backbone for synthetic KYC agents — but IBM has
> essentially no individual behavior to supply. Matching 5,000 synthetic
> Vietnamese individuals onto business-account behavior would produce retail
> customers that transact like Corporations.
>
> This is the most consequential finding of the audit and is
> `UNRESOLVED_INDIVIDUAL_BEHAVIOR`. Options are set out in the next-steps plan.

## 10. The patterns file — typology ground truth

`HI-Medium_Patterns.txt` contains 493 labeled laundering instances, each a block
of transactions bracketed by `BEGIN LAUNDERING ATTEMPT - <TYPE>` and `END`.

| Typology | Instances |
|---|---:|
| STACK | 70 |
| SCATTER-GATHER | 65 |
| BIPARTITE | 57 |
| FAN-OUT (1–16 degree) | 89 |
| FAN-IN (1–15 degree) | 66 |
| CYCLE (2–13 hops) | 66 |
| GATHER-SCATTER (1–16 degree) | 53 |
| RANDOM (1–12 hops) | 52 |

This is a substantial gift for Phase 13. It supplies scenario instances,
criminal-network membership, and typology names that would otherwise have to be
invented — the exact content of `ground_truth/scenario_instances.csv` and
`ground_truth/criminal_networks.csv`. It has not yet been parsed; that is a
Phase 13 task and is listed in the next-step plan.

## 11. What this file may and may not be used for

**May be used for:** transaction and network topology, counterparty structure,
fan-in/fan-out patterns, temporal ordering, relative amount structure within an
account, entity-to-account grouping, and laundering ground truth in the separate
`ground_truth/` subtree.

**May not be used for:** Vietnamese demographics, Vietnamese channel or currency
mix, absolute monetary scale in VND, real-world AML prevalence, or behavioral
archetypes derived with the label in scope.

Registered as `IBM_AML_HI_MEDIUM` in `data/source_registry/source_registry.yaml`.
