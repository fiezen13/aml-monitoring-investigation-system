# Data rebuild

Rebuilding the P-022 synthetic banking dataset around the IBM AML transaction
file as behavioral backbone, enriched with synthetic Vietnamese KYC profiles
derived from public statistics.

```text
IBM AML CSV -> behavioral profiling -> archetypes
                                          |
Vietnam public sources -> synthetic KYC ->  + statistical matching
                                          |
                                    canonical CSV release
```

## Status

| Phase | Status |
|---|---|
| 0 — cleanup audit | **Executed.** 6 documents and 2.9 GB of generated data removed |
| 1 — IBM dataset profile | Complete |
| 2 — account behavior profiling | Complete |
| 3 — behavioral archetypes | Complete — 5 archetypes, subsample ARI 0.998 |
| 4 — source registry | Complete — 3 sources acquired, GSO cards still registered only |
| 5 — Vietnam source profiling | Complete — 152 indicators acquired |
| 6 — individual KYC | Complete — 1,827,781 customers |
| 7 — business KYC | Complete — 249,242 businesses |
| 8 — monetary calibration | Complete — 99.6% of accounts calibrated |
| 9 — statistical matching | Complete — 2,077,023 matches, 0 reuse |
| 10-20 — canonical CSV release | **Complete.** `ABM-BANK-v0.1.0-full` — every IBM account and pattern |
| 21-25 — Kafka / Flink / HDFS | **Not started** |

The release is at `data/releases/ABM-BANK-v0.1.0-full/` (gitignored, 6.8 GB):
2,077,023 accounts and 31,901,650 transactions, covering 99.99% of the IBM
source. The earlier 6,000-account `small` slice was superseded and deleted — it
covered 1.4% of IBM and was distributionally biased by its activity band.

## Documents

| Document | Contents |
|---|---|
| [PRE_REBUILD_CLEANUP_REPORT.md](PRE_REBUILD_CLEANUP_REPORT.md) | Every artifact classified KEEP / DELETE / REVIEW_REQUIRED |
| [IBM_DATASET_PROFILE.md](IBM_DATASET_PROFILE.md) | What is measurably in the IBM file |
| [IBM_ACCOUNT_BEHAVIOR_PROFILING.md](IBM_ACCOUNT_BEHAVIOR_PROFILING.md) | Per-account behavior across 2.08M accounts |
| [IBM_BEHAVIOR_ARCHETYPES.md](IBM_BEHAVIOR_ARCHETYPES.md) | The five archetypes, how k was chosen, and their label association |
| [VIETNAM_SOURCE_PROFILING.md](VIETNAM_SOURCE_PROFILING.md) | Which Vietnamese statistics were acquired and what they support |
| [KYC_GENERATION_AND_MATCHING.md](KYC_GENERATION_AND_MATCHING.md) | How the population is generated and joined to IBM behavior |
| [MONETARY_CALIBRATION.md](MONETARY_CALIBRATION.md) | How IBM's scale becomes dong |
| [VALIDATION_AND_BIAS.md](VALIDATION_AND_BIAS.md) | Realized validation results and known synthetic bias |
| [CSV_DATA_DICTIONARY.md](CSV_DATA_DICTIONARY.md) | **Every column in the built release** |
| [RELEASE_v0.1.0-full.md](RELEASE_v0.1.0-full.md) | Row counts, checksums, validation, IBM quality comparison |
| [PROPOSED_CSV_SCHEMAS.md](PROPOSED_CSV_SCHEMAS.md) | The schema contract as proposed, before the build |
| [OPEN_QUESTIONS_AND_NEXT_STEPS.md](OPEN_QUESTIONS_AND_NEXT_STEPS.md) | Blocking questions and the ordered plan |

Tiếng Việt — dành cho cả nhóm và phía ngân hàng:

| Tài liệu | Nội dung |
|---|---|
| [PHUONG_PHAP_SYNTHETIC.md](PHUONG_PHAP_SYNTHETIC.md) | Cách sinh dữ liệu: IBM làm xương sống, nguồn VN làm KYC, và chỗ hai bên gặp nhau |
| [CHAM_DIEM_VA_TRONG_SO_AML.md](CHAM_DIEM_VA_TRONG_SO_AML.md) | Kiến trúc chấm điểm, cách suy ra trọng số (AHP + học có ràng buộc), cách agent giải thích |

Machine-readable: `data/source_registry/source_registry.yaml`,
`artifacts/source_profiles/*.json` (gitignored).

## Findings that change the design

Discovered by profiling, not anticipated:

- **IBM is 99.7% businesses.** 3,017 individual accounts out of 2,077,023.
- **The window is 27.67 days**, not the ~90 the previous design assumed.
- **Payment format predicts the laundering label** at 7.2× lift; Wire and Reinvestment never co-occur with a positive.
- **Timestamps have no daily rhythm** — every hour from 01:00 to 23:00 holds 3.88–3.90% of transactions.
- **Bank identifiers are inconsistently zero-padded**; `020` and `0020` are the same bank.
- **`HI-Medium_accounts.csv` and `HI-Medium_Patterns.txt` are unexpectedly valuable** — entity grouping with legal form, and 493 labeled typology instances.

## Commands

```bash
# Phase 1-2: profile the IBM source and every account's behavior
python -m abm.cli profile-ibm --input data/raw/ibm-aml/HI-Medium_Trans.csv
python -m abm.cli profile-ibm-behavior \
    --input    data/raw/ibm-aml/HI-Medium_Trans.csv \
    --accounts data/raw/ibm-aml/HI-Medium_accounts.csv

# Phase 3: cluster behavior into archetypes
python -m abm.cli derive-archetypes

# Phase 4-5: acquire and profile Vietnamese statistics
python -m abm.cli profile-sources

# Phase 6-9: generate KYC, match to IBM behavior, calibrate money
python -m abm.cli generate-kyc --individuals 5000 --businesses 800

# Phase 10-20: build and validate the canonical CSV release
python -m abm.cli build-release --mode full --version 0.1.0-full
python -m abm.cli validate-release --release data/releases/ABM-BANK-v0.1.0-full
python -m abm.cli compare-ibm      --release data/releases/ABM-BANK-v0.1.0-full

pytest tests/abm/ -q
```

Timings over 31.9M rows: ~40 s for the source profile; a few minutes and ~17 GB
peak memory for behavior profiling; ~10 min for archetype derivation. Source
acquisition is cached, so only the first `profile-sources` run hits the network.

## Rules

1. **`data/raw/` is immutable.** Read-only, checksummed, never regenerated.
2. **The laundering label never enters a behavioral feature.** Enforced by test.
3. **No number without a source.** A registry card marked `registered_not_acquired` may not parameterize a generator.
4. **Bank View and Ground Truth are physically separate directories.**
5. **`artifacts/` and `data/releases/` stay gitignored.** The source registry does not.
