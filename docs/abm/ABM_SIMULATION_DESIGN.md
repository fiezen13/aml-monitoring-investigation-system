# ABM simulation design

ABM-BANK v0.1.0 creates one canonical commercial-bank world for behavioral and graph research. The MVP configuration contains 10,000 customers, 1,200 merchants, about 90 days, five AML typologies, and six hard-negative families.

## Execution model

1. Load and validate configuration, sources, and parameters.
2. Generate correlated customers and businesses.
3. Create accounts, initial balances, devices, merchants, ownership, beneficial-owner, merchant, and legitimate sharing relationships.
4. Generate normal transactions by entity cohort and chronological split window.
5. Insert legitimate hard negatives.
6. Execute causal AML scenario modules that alter flows and topology.
7. Apply observation delays and configurable missingness to Bank View.
8. finalize balances, labels, networks, and split assignments.
9. Run all validation gates before writing Parquet.

Component-specific random streams derive from the release seed and namespace, avoiding accidental changes when an unrelated component consumes extra random values. Monetary values use two-decimal `Decimal`; every debit is balance-limited, and all internal credits/debits update account state.

## State and time

Agents retain segment, monthly scale, accounts, devices, split, and balances. Transactions depend on these attributes, transaction type, channel, hour, weekday, and prior available balance. Salary schedules are recurring. Each entity cohort is active only in its assigned chronological window, and networks never span splits.

## Physical views

`bank_view/` contains only bank-observable entities, sessions, relationships, transactions, and balance snapshots. `ground_truth/` contains research labels and benchmark metadata. `hidden/` contains causal intent and true coordination. Export paths and leakage tests enforce the separation.

## Scope boundaries

This is a research benchmark, not a digital twin, risk score, prevalence estimate, or reconstruction of any real person. Government/FIU and cross-border intelligence layers are out of scope.
