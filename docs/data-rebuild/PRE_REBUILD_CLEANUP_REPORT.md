# Pre-rebuild cleanup report

Audit date: 2026-08-07
Repository commit: `5b2ba91` (`develop`)
Author: Bảo (canonical dataset owner, ABM release owner)
Status: **plan only — nothing has been deleted**

## Purpose

The dataset architecture is being rebuilt around a new methodology: the IBM AML
transaction file supplies the transaction and network backbone, and synthetic
Vietnamese KYC profiles derived from public statistics are matched onto it. The
previous approach generated an entire banking world from parameter tables with
no external transaction backbone.

This report classifies every artifact of the previous approach as KEEP, DELETE,
or REVIEW_REQUIRED, so the removal can be reviewed before it happens rather
than justified afterwards.

## How to read the classifications

| Class | Meaning |
|---|---|
| KEEP | Working system, immutable source, or reusable asset. Untouched. |
| DELETE | Generated output or documentation whose method the rebuild contradicts. Safe to remove once this report is approved. |
| REVIEW_REQUIRED | Contains work worth salvaging, or a decision that is not mine alone. **Not removed under any circumstance until a named decision is recorded.** |

Two facts shape the whole list:

- `data/` and `artifacts/` are already gitignored, so every generated dataset
  below is untracked. Removing it is a filesystem operation, not a `git rm`, and
  it changes nothing about repository history.
- Only three files under `data/` are tracked: `data/README.md`,
  `data/raw/ibm-aml/README.md`, and `data/raw/ibm-aml/.gitkeep`. All three are KEEP.

## 1. Generated datasets — DELETE

| Path | Classification | Reason | Action |
|---|---|---|---|
| `data/generated/ABM-BANK-v0.2.0/` | DELETE | 2.9 GB across 128 Parquet shards and 3,586 files, produced by the from-scratch simulator. Parquet-first, no IBM lineage, and no path to the CSV-first canonical release. | Delete directory |
| `data/generated/ingestion_reports/ABM-BANK-ingestion-1786094805.json` | DELETE | Kafka ingestion report describing the release above. Meaningless once it is gone. | Delete file |

Both are untracked. Total reclaimed: about 2.9 GB.

## 2. Documentation — DELETE

Each of these describes the superseded generation method or certifies a release
that will no longer exist. Leaving them in place would leave two contradictory
methodologies documented as current.

| Path | Classification | Reason | Action |
|---|---|---|---|
| `docs/abm/ABM_BANK_V0_2_DATA_DICTIONARY.md` | DELETE | 788 lines documenting the v0.2.0 Parquet release being deleted, down to shard counts and byte sizes. | `git rm` |
| `docs/abm/ABM_SIMULATION_DESIGN.md` | DELETE | Describes generating customers, then transactions, from parameters alone. Directly contradicts the IBM-backbone design. | `git rm` |
| `docs/abm/STATISTICAL_HARMONIZATION.md` | DELETE | States that v0.1.0 deliberately avoids donor matching. The rebuild's core step *is* statistical matching. Harvest §"Source incompatibility controls" first — see below. | `git rm` after harvest |
| `docs/abm/NEXT_PHASE_IMPLEMENTATION_PLAN.md` | DELETE | Implementation plan for the superseded architecture, already executed. | `git rm` |
| `docs/abm/BEHAVIORAL_SUITABILITY_REPORT.md` | DELETE | Certifies "PASS" for a release that is being deleted. A suitability claim about absent data is worse than no claim. | `git rm` |
| `docs/abm/GRAPH_SUITABILITY_REPORT.md` | DELETE | Same as above, for graph suitability. | `git rm` |

**Harvest before deleting `STATISTICAL_HARMONIZATION.md`.** Its source
incompatibility controls — no row-level joins across public sources, survey
categories mapped with the mapping recorded as an assumption, public synthetic
datasets informing method not identity — are correct and are *more* important
under the new design, not less. They have been carried into
`docs/data-rebuild/VIETNAM_SOURCE_REGISTRY.md` and the registry's
`do_not_use_for` fields.

## 3. Documentation — KEEP

These state policies that survive the methodology change intact.

| Path | Classification | Reason | Action |
|---|---|---|---|
| `docs/abm/GROUND_TRUTH_POLICY.md` | KEEP | Bank View / ground-truth / hidden separation. The rebuild strengthens this rule; it does not replace it. | Preserve, revise for CSV paths |
| `docs/abm/HARD_NEGATIVES.md` | KEEP | Six hard-negative families with legitimate explanations and rule collisions. Phase 15 consumes this directly. | Preserve |
| `docs/abm/DATASET_SPLIT_POLICY.md` | KEEP | Entity/network/time splitting, never row-random. Phase 16 keeps the rule; the time fractions need revision for IBM's 28-day window. | Preserve, revise |
| `docs/abm/PARAMETER_METHODOLOGY.md` | KEEP | The parameter-card system with source IDs, confidence, and sensitivity ranges. Reusable as-is and enforced by `abm/registry.py`. | Preserve |
| `docs/abm/PUBLIC_SOURCE_REGISTER.md` | KEEP | Prose companion to the source registry. Superseded in place by the Vietnam-focused registry rather than deleted. | Preserve, supersede |

## 4. Documentation — REVIEW_REQUIRED

| Path | Classification | Reason | Action |
|---|---|---|---|
| `docs/abm/CANONICAL_DATA_MODEL.md` | REVIEW_REQUIRED | The CUSTOMER/BUSINESS separation, time-aware relationships, and tokenized external counterparties are good design that the new CSV schemas should inherit. But it is Parquet-oriented and has no IBM lineage concept. | **Do not delete.** Supersede once the new schema doc is approved |
| `docs/abm/ABM_RELEASE_RUNBOOK.md` | REVIEW_REQUIRED | Documents `make abm-*` commands that will change. Needs rewriting, not deleting. | **Do not delete.** Rewrite |
| `docs/abm/ABM_REPOSITORY_AUDIT.md` | REVIEW_REQUIRED | The previous Phase 0 audit. It is a historical record of a decision, and its finding that the repository holds three distinct data worlds is still true and still useful. | **Do not delete.** Bảo decides whether audits are retained as history |

## 5. Code — REVIEW_REQUIRED

None of this is deleted in this pass. The rebuild needs working matching and
export code before removing the code it replaces; deleting first would leave the
repository with no generator at all.

| Path | Lines | Classification | Reason |
|---|---:|---|---|
| `abm/generator.py` | 1,077 | REVIEW_REQUIRED | Generates the world from parameters with no transaction backbone. This is the component the rebuild replaces. Retire only when the IBM-backed pipeline produces a validated release. |
| `abm/large_release.py` | 297 | REVIEW_REQUIRED | Sharded multi-GB Parquet builder for v0.2.0. Superseded by CSV-first, but its bounded-memory shard pattern is worth reading before writing the CSV exporter. |
| `abm/exporters/release.py` | 347 | REVIEW_REQUIRED | Parquet exporter and manifest verification. The manifest/checksum logic transfers to CSV directly. |
| `abm/release.py` | 66 | REVIEW_REQUIRED | Thin orchestration over the above. |
| `abm/models.py` | 80 | REVIEW_REQUIRED | Dataclasses for the old canonical model. Partly reusable. |
| `abm/validation/release.py` | 393 | REVIEW_REQUIRED | Primary/foreign key, temporal, monetary, and leakage gates. **Most of Phase 18 already exists here.** Port rather than rewrite. |
| `abm/observation/engine.py` | 52 | REVIEW_REQUIRED | Observation delay and missingness. Still wanted in Phase 12. |
| `abm/scenarios/engine.py` | 520 | REVIEW_REQUIRED | AML typology injection. Its role changes: IBM now supplies the topology, so this becomes scenario *extension* rather than the primary source. |
| `abm/scenarios/hard_negatives.py` | 420 | REVIEW_REQUIRED | Phase 15 consumes this. Likely KEEP after review. |
| `abm/configs/{tiny,mvp,large}.yaml` | 57 | REVIEW_REQUIRED | Configs for releases that will not be rebuilt. Replaced by a `small.yaml` keyed to an IBM subset. |
| `tests/abm/*` (4 files) | — | REVIEW_REQUIRED | Test the current generator and release layout. They must keep passing until their subject is retired. |

## 6. Code and infrastructure — KEEP

| Path | Classification | Reason |
|---|---|---|
| `data/raw/ibm-aml/` | KEEP | **Immutable source evidence.** `HI-Medium_Trans.csv`, `HI-Medium_accounts.csv`, `HI-Medium_Patterns.txt`. Never modified, never regenerated, checksummed in the source profile. |
| `tests/fixtures/aml/HI-Sample_Trans.csv` | KEEP | 203-row committed fixture with deliberately malformed rows for DLQ tests. Small, deterministic, tracked — exactly the kind of fixture that belongs in Git. |
| `src/aml/` | KEEP | Working IBM CSV → Kafka producer. `csvsource.py` solves the duplicate-`Account`-column problem by positional reading; the new profiler reuses that contract. |
| `flink/aml-ingestion/` | KEEP | Working Flink job. Phase 25 feeds it, does not rebuild it. |
| `contracts/` | KEEP | Event, canonical, agent, and ingestion JSON schemas. Some need v3 additions; none need deleting. |
| `abm/registry.py`, `abm/parameters/*.yaml` | KEEP | Parameter-card registry with source-ID enforcement. The rebuild needs more of this, not less. |
| `abm/sources/source_registry.yaml` | KEEP | Existing source cards, including four Vietnamese sources. Migrated forward, not rewritten. |
| `abm/adapters/{events,kafka}.py` | KEEP | Release → Kafka adapter. Phase 25 retargets it at CSV. |
| `abm/profiling/profile_source.py` | KEEP | Generic CSV/Parquet profiler, still used for the Vietnam sources. |
| `scripts/aml/` | KEEP | Dataset download, topic creation, HDFS/Kafka inspection, smoke tests. |
| `scripts/abm_generate.py` | KEEP | Generates the `VN-CA-03` demo case into PostgreSQL for the UI. A different data world from the canonical release; the previous audit already established this. Not part of the rebuild. |
| `scripts/seed_data.py` | KEEP | Deterministic UI/demo fixture. |
| `src/`, `web/`, `services/`, `db/`, `deploy/`, `docker/`, `ci/`, `jenkins/`, `.github/` | KEEP | Application, frontend, infrastructure, CI/CD. Out of scope. |
| `tests/` except `tests/abm/` | KEEP | Unrelated to ABM generation. |

## 7. Out of scope, noted only

`.coverage`, `coverage.xml`, and `pytest-report.xml` sit untracked in the
repository root. They are gitignored build output, unrelated to the ABM rebuild,
and this report does not propose touching them.

## 8. Summary

| Class | Tracked files | Untracked paths | Bytes |
|---|---:|---:|---:|
| DELETE | 6 documents | 2 directories | ~2.9 GB |
| REVIEW_REQUIRED | 3 documents, 11 code paths | — | — |
| KEEP | everything else | `data/raw/ibm-aml/` | 3.0 GB source |

**Nothing in this report has been executed.** The DELETE rows are safe to apply
once approved. The REVIEW_REQUIRED rows must not be applied at all until a named
decision is recorded against each one.
