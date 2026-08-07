# Dataset split policy

ABM-BANK never randomly splits transaction rows. Each customer receives one deterministic entity cohort: `TRAIN`, `VALIDATION`, `TEST`, or `HIDDEN_TEST`. Accounts and devices inherit the owner cohort; merchants inherit their operating business cohort; scenarios and complete networks are allocated to exactly one cohort.

Within the 90-day MVP, activity uses non-overlapping chronological windows:

| Split | Entity allocation | Time fraction |
|---|---:|---:|
| TRAIN | 70% | first 60% |
| VALIDATION | 10% | next 20% |
| TEST | 10% | next 10% |
| HIDDEN_TEST | 10% | final 10% |

The proportions are registered governance parameters. Bank transactions are checked so every internal endpoint has the same split as the event. Scenario IDs, network IDs, labels, and members must also agree. This prevents direct entity, network, and future-time leakage at the cost of distribution shift between windows—a desirable property for evaluation.

Track teams may derive specialized datasets only from `ground_truth/split_assignments.parquet`. They may group or withhold splits but must not reassign individual transaction rows across these boundaries.
