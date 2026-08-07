# Proposed canonical CSV schemas

Status: **proposed for approval**. No generator writes these yet.

This is the schema contract for `ABM-BANK-v0.1.0-small`. It becomes the full
data dictionary (Phase 17) once approved; it is presented now because the schema
is the interface Hường and Hiển both build against, and changing it later is
expensive for both.

## Release layout

```text
data/releases/ABM-BANK-v0.1.0-small/
    bank_view/       customers, businesses, accounts, transactions,
                     devices, merchants, relationships
    ground_truth/    entity_labels, scenario_instances, criminal_networks,
                     transaction_labels
    splits/          train_entities, validation_entities,
                     test_entities, hidden_test_entities
    reports/         quality_report, source_alignment_report,
                     behavioral_validation, graph_validation
    manifest.json
```

The split between `bank_view/` and `ground_truth/` is physical, not a
convention. A directory boundary is enforceable by a test; a naming convention
is not.

## Conventions

| Rule | Value |
|---|---|
| Encoding | UTF-8, no BOM |
| Header | required, first line |
| Delimiter | `,` |
| Quoting | minimal; any field containing `,`, `"`, or a newline is quoted |
| Line ending | `\n` |
| Timestamps | ISO-8601 with offset, e.g. `2022-09-01T00:17:00+07:00` |
| Dates | ISO-8601 `YYYY-MM-DD` |
| Null | empty field. Never `NULL`, `NA`, `None`, or `-` |
| Booleans | `true` / `false` |
| Decimals | plain digits with `.`, no thousands separator, no currency symbol |
| Leading `=`, `+`, `-`, `@` | prefixed fields are quoted, so spreadsheets do not evaluate them |

### Identifiers

| Prefix | Entity | Example |
|---|---|---|
| `CUS-` | customer (individual) | `CUS-00000001` |
| `BIZ-` | business | `BIZ-00000001` |
| `ACC-` | account | `ACC-00000001` |
| `TXN-` | transaction | `TXN-000000000001` |
| `DEV-` | device | `DEV-00000001` |
| `MER-` | merchant | `MER-00000001` |
| `SCN-` | scenario instance | `SCN-00000001` |
| `NET-` | criminal network | `NET-00000001` |

Zero-padded, monotonically assigned in a deterministic order derived from the
release seed. **No IBM account identifier appears anywhere in a release file.**
The mapping from `ACC-*` back to `bank:account` lives only in
`artifacts/intermediate/account_lineage.csv`, which is gitignored and is not
part of any release.

---

## Bank View

### `bank_view/customers.csv`

Individuals. No AML field appears here.

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `customer_id` | string | no | generated | `CUS-*`. Primary key |
| `customer_type` | enum | no | generated | `INDIVIDUAL` |
| `age_band` | enum | no | VN_GSO_POPULATION_2024 | `15-24`,`25-34`,`35-44`,`45-54`,`55-64`,`65+` |
| `gender` | enum | no | VN_GSO_POPULATION_2024 | `F`,`M` |
| `region` | enum | no | VN_GSO_POPULATION_2024 | Socio-economic region code |
| `urban_rural` | enum | no | VN_GSO_POPULATION_2024 | `URBAN`,`RURAL`; conditioned on region |
| `occupation_group` | enum | yes | VN_GSO_LFS_2024 | Null when not employed |
| `employment_status` | enum | no | VN_GSO_LFS_2024 | `WAGE_WORKER`,`OWN_ACCOUNT`,`EMPLOYER`,`UNPAID_FAMILY`,`NOT_EMPLOYED` |
| `income_band` | enum | yes | VN_GSO_LFS_2024, VN_GSO_VHLSS_2022 | Monthly VND band |
| `financial_access_segment` | enum | no | VN_WB_FINDEX_2024 | `FULL`,`BASIC`,`LIMITED` |
| `digital_usage_segment` | enum | no | VN_WB_FINDEX_2024 | `HIGH`,`MEDIUM`,`LOW`,`NONE` |
| `expected_monthly_income_band` | enum | yes | derived | Calibration input for Phase 8 |
| `expected_monthly_turnover_band` | enum | no | derived | Calibration input for Phase 8 |
| `customer_archetype` | enum | no | derived (Phase 3) | Behavioral archetype assigned by matching |
| `customer_tenure_band` | enum | no | generated | `<1Y`,`1-3Y`,`3-5Y`,`5Y+` |
| `residency_status` | enum | no | generated | `RESIDENT`,`NON_RESIDENT` |

No name, national ID, phone number, address, or date of birth. Not
pseudonymized — **absent**. Bands carry every attribute the models need, and a
field that does not exist cannot leak.

### `bank_view/businesses.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `business_id` | string | no | generated | `BIZ-*`. Primary key |
| `legal_form` | enum | no | VN_GSO_ENTERPRISE_2024 | `LLC`,`JSC`,`PARTNERSHIP`,`SOLE_PROPRIETOR`,`HOUSEHOLD_BUSINESS` |
| `industry_group` | enum | no | VN_GSO_ENTERPRISE_2024 | VSIC section level |
| `region` | enum | no | VN_GSO_ENTERPRISE_2024 | |
| `business_age_band` | enum | no | VN_GSO_ENTERPRISE_2024 | `<1Y`,`1-3Y`,`3-10Y`,`10Y+` |
| `employee_size_band` | enum | no | VN_GSO_ENTERPRISE_2024 | `1-9`,`10-49`,`50-199`,`200+` |
| `revenue_band` | enum | no | VN_GSO_ENTERPRISE_2024 | Annual VND band |
| `expected_monthly_turnover_band` | enum | no | derived | Calibration input |
| `cash_intensity_band` | enum | no | derived | `LOW`,`MEDIUM`,`HIGH` |
| `digital_payment_intensity` | enum | no | VN_SBV_PAYMENT_STATISTICS | `LOW`,`MEDIUM`,`HIGH` |
| `domestic_international_profile` | enum | no | generated | `DOMESTIC_ONLY`,`MIXED`,`INTERNATIONAL_HEAVY` |
| `business_archetype` | enum | no | derived (Phase 3) | |

Business revenue is drawn from enterprise statistics. Individual income
distributions are never reused for business revenue.

### `bank_view/accounts.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `account_id` | string | no | generated | `ACC-*`. Primary key |
| `owner_id` | string | no | generated | FK to `customer_id` or `business_id` |
| `owner_type` | enum | no | generated | `CUSTOMER`,`BUSINESS` |
| `account_type` | enum | no | generated | `CURRENT`,`SAVINGS`,`BUSINESS_CURRENT` |
| `currency` | enum | no | fixed | `VND` for v0.1.0 |
| `open_date` | date | no | generated | Strictly before the account's first transaction |
| `status` | enum | no | generated | `ACTIVE`,`DORMANT`,`CLOSED` |
| `behavior_archetype` | enum | no | derived (Phase 3) | Archetype of the matched IBM behavior |
| `expected_monthly_turnover_band` | enum | no | derived | |

`owner_id` + `owner_type` is a typed foreign key rather than two nullable
columns, so "exactly one owner" is expressible as a validation rule.

### `bank_view/transactions.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `transaction_id` | string | no | generated | `TXN-*`. Primary key |
| `event_id` | string | no | generated | Deterministic hash; the Kafka dedup key |
| `schema_version` | string | no | fixed | `1.0` |
| `timestamp` | timestamp | no | IBM (shifted) | ISO-8601 with `+07:00` |
| `source_account_id` | string | yes | IBM (mapped) | FK to accounts; null when external |
| `destination_account_id` | string | yes | IBM (mapped) | FK to accounts; null when external |
| `source_counterparty_token` | string | yes | generated | `CPY-*` when the source is outside the bank |
| `destination_counterparty_token` | string | yes | generated | `CPY-*` when the destination is outside the bank |
| `amount` | decimal(18,2) | no | IBM (calibrated) | VND, always > 0 |
| `currency` | enum | no | fixed | `VND` |
| `payment_format` | enum | no | **see note** | Vietnamese channel taxonomy |
| `channel` | enum | no | derived | `MOBILE`,`INTERNET`,`ATM`,`BRANCH`,`POS`,`QR` |
| `transaction_type` | enum | no | derived | `TRANSFER`,`DEPOSIT`,`WITHDRAWAL`,`PURCHASE`,`SALARY`,`FEE` |
| `merchant_id` | string | yes | generated | FK to merchants, for `PURCHASE` |

Exactly one of `source_account_id` / `source_counterparty_token` is populated,
and likewise for the destination. That makes "an endpoint is either internal or
external, never both and never neither" a checkable constraint.

> **`payment_format` is blocked pending a decision.** IBM's format predicts its
> own laundering label at 7.2× lift, with two values that never co-occur with a
> positive label (Finding L1). It cannot be copied across.
> See `UNRESOLVED_PAYMENT_FORMAT_LEAKAGE`.

**Never present in this file:** `is_laundering`, `scenario_id`, `true_role`,
`criminal_network_id`, or any IBM account identifier. A test asserts the column
set contains none of them.

### `bank_view/devices.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `device_id` | string | no | generated | `DEV-*`. Primary key |
| `customer_id` | string | no | generated | FK to customers |
| `device_type` | enum | no | generated | `ANDROID`,`IOS`,`WEB` |
| `first_seen` | timestamp | no | generated | |
| `last_seen` | timestamp | no | generated | |

Device distributions must overlap between normal and suspicious customers. A
device attribute that separates them is a synthetic tell, and Phase 14 fails on
it.

### `bank_view/merchants.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `merchant_id` | string | no | generated | `MER-*`. Primary key |
| `merchant_category` | enum | no | VN_GSO_ENTERPRISE_2024 | MCC-style group |
| `region` | enum | no | VN_GSO_ENTERPRISE_2024 | |
| `operated_by_business_id` | string | yes | generated | FK to businesses |

### `bank_view/relationships.csv`

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `relationship_id` | string | no | generated | Primary key |
| `source_entity_id` | string | no | generated | Any entity ID |
| `source_entity_type` | enum | no | generated | `CUSTOMER`,`BUSINESS`,`ACCOUNT`,`DEVICE`,`MERCHANT` |
| `destination_entity_id` | string | no | generated | |
| `destination_entity_type` | enum | no | generated | |
| `relationship_type` | enum | no | generated | `OWNS`,`USES_DEVICE`,`BENEFICIARY`,`BUSINESS_OWNER`,`SHARES_DEVICE` |
| `valid_from` | timestamp | no | generated | |
| `valid_to` | timestamp | yes | generated | Null means currently valid |

Time-aware edges. `valid_to` null means open, which is why it is the one
nullable column here.

---

## Ground Truth

Physically separate. Never joined into Bank View by the generator.

### `ground_truth/entity_labels.csv`

| Column | Type | Null | Description |
|---|---|---|---|
| `entity_id` | string | no | `ACC-*`, `CUS-*`, or `BIZ-*` |
| `entity_type` | enum | no | `ACCOUNT`,`CUSTOMER`,`BUSINESS` |
| `label_type` | enum | no | `IBM_AML_INVOLVEMENT`,`HARD_NEGATIVE`,`SCENARIO_ROLE` |
| `label_value` | string | no | `1`/`0`, or a role name |
| `active_from` | timestamp | no | |
| `active_to` | timestamp | yes | |
| `source` | enum | no | `IBM_AML`,`IBM_PATTERNS`,`P022_SIMULATION` |

Roles, stages, and intervals stay normalized. A single flattened binary label is
derived downstream for a declared prediction target and point in time — the
release does not choose that target on the consumer's behalf.

### `ground_truth/transaction_labels.csv`

| Column | Type | Null | Description |
|---|---|---|---|
| `transaction_id` | string | no | FK to Bank View transactions |
| `is_laundering` | boolean | no | From the IBM label |
| `scenario_id` | string | yes | FK to scenario instances |
| `scenario_stage` | enum | yes | `PLACEMENT`,`LAYERING`,`INTEGRATION` |
| `source` | enum | no | `IBM_AML`,`IBM_PATTERNS`,`P022_SIMULATION` |

### `ground_truth/scenario_instances.csv`

| Column | Type | Null | Description |
|---|---|---|---|
| `scenario_id` | string | no | `SCN-*`. Primary key |
| `typology` | enum | no | `STACK`,`SCATTER-GATHER`,`BIPARTITE`,`FAN-IN`,`FAN-OUT`,`CYCLE`,`GATHER-SCATTER`,`RANDOM` |
| `typology_parameter` | string | yes | e.g. `max 12 hops`, `9-degree` |
| `network_id` | string | yes | FK to criminal networks |
| `first_event` / `last_event` | timestamp | no | |
| `transaction_count` | integer | no | |
| `split` | enum | no | The one split this instance belongs to |
| `source` | enum | no | `IBM_PATTERNS` for the 493 parsed instances |

Typology values are taken from `HI-Medium_Patterns.txt` rather than invented.

### `ground_truth/criminal_networks.csv`

| Column | Type | Null | Description |
|---|---|---|---|
| `network_id` | string | no | `NET-*`. Primary key |
| `member_entity_id` | string | no | |
| `member_entity_type` | enum | no | |
| `true_role` | enum | no | `ORIGINATOR`,`MULE`,`CONTROLLER`,`BENEFICIARY`,`PASSTHROUGH` |
| `scenario_id` | string | no | FK to scenario instances |

---

## Splits

`splits/{train,validation,test,hidden_test}_entities.csv`, identical schema:

| Column | Type | Null | Description |
|---|---|---|---|
| `entity_id` | string | no | |
| `entity_type` | enum | no | `CUSTOMER`,`BUSINESS` |
| `split` | enum | no | Redundant with the filename, deliberately |

Split by entity and network, never by transaction row. Accounts and devices
inherit their owner's split. A criminal network sits entirely in one split.

> Phase 16 also asks for a chronological split. With a 27.67-day window
> (Finding T1) the four chronological slices would be roughly 17/6/3/3 days —
> too short for the rolling-window features Hường needs. **Recommendation: split
> by entity and network only for v0.1.0**, and record the absence of a
> chronological split as a known limitation rather than shipping windows too
> short to be useful.

---

## `manifest.json`

```json
{
  "dataset_id": "ABM-BANK",
  "dataset_version": "0.1.0-small",
  "created_at": "...",
  "generator_git_commit": "...",
  "seed": 20260807,
  "schema_version": "1.0",
  "ibm_source": {
    "filename": "HI-Medium_Trans.csv",
    "sha256": "3126afb8155e7c8815d62bc5370549a7b5ae6bf7dfe872b3cd7813e66a3d7ff5",
    "rows_in_source": 31898238,
    "rows_selected": null
  },
  "public_sources": ["VN_GSO_POPULATION_2024", "..."],
  "source_registry_version": "0.1.0",
  "counts": {
    "customers": null, "businesses": null, "accounts": null,
    "transactions": null, "ground_truth_labels": null
  },
  "split_counts": {},
  "file_checksums": {},
  "known_limitations": [],
  "release_owner": "Bao"
}
```

`known_limitations` is required and must not be empty. The observation window,
the individual/business imbalance, and the payment-format decision all belong
there in whatever form they are resolved.
