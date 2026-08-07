# Hard negatives

Hard negatives are legitimate episodes designed to collide with simplistic AML rules. They are generated before AML typologies and remain explicitly separate from suspicious ground truth.

| Family | Legitimate explanation | Observable collision |
|---|---|---|
| Salary disbursement | Registered business funds and pays an employee cohort | Fan-out, many beneficiaries, rapid balance decline |
| Marketplace seller | Seller receives many small customer payments then settles costs | Fan-in, bursty receipts, counterparty diversity |
| Family remittance hub | Household member collects and redistributes family funds | Hub topology and rapid redistribution |
| Seasonal business | A business has a short high-volume seasonal peak | Sudden peer deviation and cash/merchant bursts |
| Property or insurance event | Documented large one-off proceeds and subsequent payments | Large inbound followed by rapid outflows |
| Treasury movement | Related businesses sweep liquidity | High-value pass-through and circular movement |

Each row in `ground_truth/hard_negative_instances.parquet` records the family, explanation, observable pattern, likely rule collision, entity and transaction IDs, active interval, split, and `LEGITIMATE` ground truth. Quotas are registered benchmark coverage decisions. Hard-negative entities are excluded from AML actor selection so labels cannot conflict.
