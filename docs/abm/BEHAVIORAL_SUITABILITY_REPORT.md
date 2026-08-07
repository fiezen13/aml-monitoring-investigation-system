# Behavioral suitability report

Status for v0.1.0 design: **PASS**, subject to the generated release quality report.

Bank View supplies event time, posting time, observation availability time, exact amount/currency, transaction type, channel, two exclusive endpoint pairs, account ownership, device/session where observed, merchant, purpose where observed, balances, and stable split assignments. These fields support point-in-time derivation of:

- transaction count and amount windows;
- unique and new counterparty counts;
- credit/debit ratios and balance turnover;
- inflow-to-outflow dwell time and rapid movement;
- night/weekend activity;
- channel, merchant, device, and purpose changes;
- peer baselines by customer segment and business scale.

`available_from` prevents using delayed data before the bank could observe it. Opening/closing snapshots permit reconciliation, while transactions permit intermediate rolling balances. Missing device and purpose fields are explicit observation outcomes, not hidden truth.

No label, scenario, network, role, controller, or hidden-intent field is required for features. Labels are joined only after feature materialization for evaluation. The release validator checks required columns, temporal ordering, coverage of types/channels, observation rates, accounting, and hidden-column leakage; realized results are in `reports/behavioral_suitability_report.json` and `quality_report.json`.
