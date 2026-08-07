# ABM-BANK next-phase implementation plan

Status: proposed; execution starts only after Phase 0-2 review

Target release: `ABM-BANK-v0.1.0`

Target scale: 5,000-10,000 customers, approximately 90 simulated days

## Review gate

Before implementation, approve or amend:

1. the canonical CUSTOMER/BUSINESS separation;
2. canonical v2 customer/account/relationship contracts;
3. stable tokenized external counterparty nodes;
4. the physical Bank View/ground-truth/hidden separation;
5. a new label-free Kafka ingestion route or versioned Flink migration;
6. the public sources and their permitted/prohibited uses;
7. whether a protected aggregate sample from a Vietnamese bank can be provided for calibration.

No numeric AML prevalence will be modeled. Scenario counts will be explicit benchmark quotas with sensitivity variants.

## Proposed repository changes

```text
abm/
  cli.py
  configs/
    tiny.yaml
    mvp.yaml
  sources/
    source_registry.yaml
  profiling/
  parameters/
  harmonization/
  generators/
    population/
    behavior/
  scenarios/
  observation/
  ground_truth/
  validation/
  exporters/
  adapters/

tests/abm/
docs/abm/
contracts/canonical/
```

Directories will be added only when their first working component is added. Large source and release artifacts remain outside Git. `.gitignore` will explicitly ignore `artifacts/ABM-BANK-v*/`, profile data extracts, checkpoints, and simulator scratch files while preserving small deterministic fixtures.

## Step 3 — public source profiling

Deliverables:

- `abm/profiling/profile_source.py` CLI;
- source-specific readers with streaming/chunked operation;
- numerical, categorical, temporal, transaction, and graph profiles;
- `summary.json`, distribution JSON files, and a Markdown report;
- a profile manifest containing source ID/version, input checksum, profiler commit/version, configuration, and output checksums;
- tests using only tiny deterministic fixtures.

Required safeguards:

- no source file committed;
- decimal and identifier types preserved;
- duplicate IBM `Account` headers handled by position;
- no label column included in normal-behavior profile inputs unless explicitly profiled as ground truth;
- weighted survey estimates used where required;
- source scope and prohibited uses copied into every profile.

Exit gate: running the profiler twice against the same source/version/config produces identical machine-readable statistics within a declared numeric tolerance.

## Step 4 — Parameter Registry

Deliverables:

- parameter files for population, businesses, accounts, devices, normal transactions, temporal behavior, networks, observation, and scenario quotas;
- JSON Schema or Pydantic validation for parameter cards;
- `python -m abm.cli validate-parameters`;
- a dependency graph from source profile statistic to parameter;
- explicit assumption cards with reason, confidence, sensitivity range, and modeled effect.

No important numeric value may appear only in Python. Enum labels, mathematical identities, and array indices are code constants; behavioral probabilities, counts, distributions, thresholds, and delays are registered parameters.

Exit gate: static/runtime validation fails when a generator requests an unregistered parameter or a parameter has neither a source statistic nor an assumption record.

## Step 5 — statistical harmonization

Initial method set:

- iterative proportional fitting for compatible published margins;
- weighted conditional tables for age/region/employment/digital use;
- donor/statistical matching across sources only through shared categories, never row identity;
- fitted within-band distributions with documented truncation;
- empirical conditional resampling where a suitable transaction source exists;
- transition/intensity models for time behavior;
- graph-statistic targets used as validation objectives, not copied edges.

Deliverables:

- `docs/abm/STATISTICAL_HARMONIZATION.md`;
- harmonized joint-distribution artifacts with checksums;
- marginal and conditional fit tests;
- sensitivity analysis for weak assumptions.

Exit gate: generated marginal and conditional tables reproduce selected targets within registered tolerances, with every mismatch reported.

## Steps 6-7 — normal population and relationships

Generation order:

1. bank portfolio selection from harmonized national margins;
2. individual customers and separate businesses;
3. customer/business bank relationships;
4. accounts and opening balances;
5. merchants;
6. devices and session propensity;
7. employment, ownership, known beneficiary, and other legitimate relationships.

Implementation rules:

- one named RNG stream per component derived deterministically from the release seed;
- stable IDs independent of output row order;
- dependent attributes drawn conditionally;
- no AML role selected during normal population generation;
- scenarios select eligible actors later without mutating immutable identity facts;
- foreign keys validated before behavior generation.

Exit gate: uniqueness, referential, lifecycle, impossible-value, and deterministic-checksum tests pass on the tiny configuration.

## Step 8 — normal financial behavior

The first release will implement only behavior supported by the canonical schema and evidence:

- salary;
- household transfers;
- bill payments;
- merchant purchases;
- cash deposit/withdrawal;
- business and supplier payments;
- loan repayment;
- savings transfer;
- international payment only if parameters pass evidence review.

Each agent maintains balances, scheduled obligations, recent activity, known counterparties, regular merchants, and business cycles. Transactions are emitted from state transitions, not independent uniform draws.

Exit gate:

- all amounts are positive exact decimals;
- no transaction predates account opening;
- posting/reversal semantics are consistent;
- account ledger equations hold exactly;
- temporal, amount, channel, counterparty, and degree distributions are compared quantitatively to source profiles.

The transaction count for the MVP is not fixed in this plan. It will be the result of registered activity-rate distributions over the approved 5,000-10,000 customer and ~90-day scope, followed by a development-machine memory/runtime gate.

## Step 9 — hard negatives

Initial candidates:

- salary-disbursement employer;
- popular marketplace seller;
- family remittance hub;
- seasonal/high-volume merchant;
- property sale or insurance payout;
- legitimate business treasury movement.

Every instance records its legitimate reason in ground truth only, while Bank View contains the ambiguous observable pattern. Counts are benchmark quotas, not prevalence estimates.

Exit gate: each AML scenario has at least one topology/behavior-matched legitimate control and quality reports break out false-positive behavior on those controls.

## Steps 10-12 — scenario engine, hidden state, and ground truth

First reviewed scenario candidates:

- structuring;
- rapid pass-through;
- mule/funnel network;
- fan-in/fan-out collection;
- circular/layering flow.

Each scenario module defines roles, eligibility, timeline, topology, state transitions, observable effects, hidden intent, evidence references, and parameter IDs. It alters behavior and network structure; it never labels unchanged normal transactions.

Physical outputs:

```text
simulation_output/
  hidden/
  bank_view/
  ground_truth/
```

Ground truth remains multi-label and time-aware at entity, transaction, edge, network, and scenario-instance levels. Scenario frequency is reported as intentional benchmark insertion count.

Exit gate: architecture tests inspect schemas, Parquet columns, import graphs, and output paths for prohibited hidden fields.

## Step 13 — observation engine

Configurable rules will model only documented bank limitations:

- missing/delayed customer fields;
- partial device/session coverage;
- unknown external counterparties;
- coarse rather than exact locations;
- uncertain inferred relationships;
- channel-specific availability time.

Exit gate: all information has an `available_from` or equivalent known time, no feature-visible record exists before it is observable, and observation noise stays within registered rules.

## Steps 14-16 — validation and split policy

Automated reports:

- schema and enum checks;
- primary/foreign-key checks;
- temporal integrity;
- exact ledger reconciliation;
- source-profile statistical comparison;
- graph node/edge/degree/component/community/temporal checks;
- behavioral feature-derivability checks;
- hidden-column and import-boundary leakage checks;
- time/entity/scenario/network-safe split checks.

Proposed split hierarchy:

- chronological boundaries first;
- hold out scenario instances and entire criminal networks;
- reserve entity cohorts for hidden test;
- never randomly split transaction rows;
- publish canonical assignments that both ML tracks inherit.

Exit gate: all required quality gates emit machine-readable pass/fail results; no report is manually declared green.

## Step 17 — release

Release command target:

```bash
python -m abm.cli generate --config abm/configs/mvp.yaml --seed 20260807 --output artifacts
python -m abm.cli validate --release artifacts/ABM-BANK-v0.1.0
python -m abm.cli release --release artifacts/ABM-BANK-v0.1.0
```

Manifest content:

- dataset/version/schema versions;
- generator commit and dirty-tree status;
- simulation seed and interval;
- source/profile/parameter registry versions and checksums;
- record and scenario-instance counts;
- file checksums and sizes;
- validation gate results;
- release owner, timestamp, and known limitations.

Parquet will be partitioned by event date for transactions and written in bounded batches. Master tables are single files at MVP scale. The complete release is ignored by Git.

Exit gate: same clean commit, config, profiles, parameter registry, and seed reproduce identical logical content checksums. Parquet byte checksums will be required only if writer metadata is also deterministic; otherwise canonical row/content hashes are authoritative and the distinction is documented.

## Step 18 — Kafka/Flink/HDFS integration

Preferred path:

1. canonical Bank View transaction;
2. adapter to `bank.transaction.posted.v1` in `envelope.v1`;
3. versioned label-free Kafka topic;
4. existing Flink code extended through a reviewed new source model or a parallel small adapter job;
5. existing HDFS conventions.

The legacy IBM topic will remain unchanged for compatibility. No hidden label is emitted. A tiny deterministic batch proves counts, IDs, rejection handling, UTC partitioning, and no hidden columns at HDFS.

Exit gate: the exact tiny-run event IDs emitted by the ABM are present in HDFS with no extras/missing records after deduplication rules are applied.

## CI and local profiles

| Profile | Purpose | Size |
|---|---|---|
| tiny | Unit/CI determinism and invariants | hundreds of customers, short period, bounded transactions |
| small | Developer smoke and integration | approximately 1,000 customers |
| mvp | Release candidate | 5,000-10,000 customers, ~90 days |

Only `tiny` runs in normal CI. Kafka integration may run in a dedicated service-capable job. MVP generation is a release operation, not a merge-gate test.

## Unresolved assumptions

- Exact bank portfolio selection from national population sources is unknown.
- Account/product counts per customer lack a strong Vietnamese public source.
- Customer-level amount/frequency/inter-arrival distributions lack a suitable Vietnamese source.
- Device ownership, token stability, and session observability need evidence or protected calibration.
- Merchant population/MCC mix and business payment cycles need stronger data.
- Scenario numeric details such as actor count, dwell time, retention percentage, and episode duration will require low-confidence sensitivity cards unless a better source is approved.
- Legal/reporting thresholds are jurisdiction- and date-specific; none will be imported from US examples.
- The existing pipeline's label-bearing raw contract requires a versioned integration decision.

These are explicit blockers to parameter values, not blockers to building the profiling and registry infrastructure after review.
