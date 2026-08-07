# CSV data dictionary — ABM-BANK-v0.1.0-small

Every column in the release. Types are logical; CSV carries text, and this is
what a reader should cast to.

## Conventions

| Rule | Value |
|---|---|
| Encoding | UTF-8, no BOM |
| Header | required, first line |
| Delimiter | `,` — quoting only where needed |
| Line ending | `\n` |
| Timestamps | ISO-8601 with offset, `2022-09-01T00:00:10+07:00` |
| Dates | `YYYY-MM-DD` |
| Null | empty field. Never `NULL`, `NA`, `None`, `-` |
| Booleans | `true` / `false` |
| Money | integer VND. No decimals — dong has no circulating subunit |
| Formula guard | values starting `=`, `+`, `-`, `@` are prefixed with `'` |

**View** column below: `BV` = Bank View (safe for feature engineering),
`GT` = Ground Truth (evaluation only, never a model input).

## Identifiers

| Prefix | Entity | Format |
|---|---|---|
| `CUS-` | individual customer | `CUS-00000001` |
| `BIZ-` | business | `BIZ-00000001` |
| `ACC-` | account | `ACC-00000001` |
| `TXN-` | transaction | `TXN-000000000001` |
| `CPY-` | external counterparty token | `CPY-00000001` |
| `DEV-` | device | `DEV-00000001` |
| `MER-` | merchant | `MER-00000001` |
| `REL-` | relationship | `REL-0000000001` |
| `SCN-` | scenario instance | `SCN-000001` |
| `NET-` | criminal network | `NET-000001` |
| `HNG-` | hard-negative episode | `HNG-000001` |

**No IBM identifier appears anywhere in the release.** An IBM account key is
`bank:account`; a test asserts no colon-bearing identifier survives.

---

# Bank View

## `bank_view/customers.csv` — 5,280 rows

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `customer_id` | string | no | generated | Primary key |
| `customer_type` | enum | no | generated | `INDIVIDUAL` |
| `age_band` | enum | no | WDI `SP.POP.*.5Y` | `15-24`…`65+` |
| `gender` | enum | no | WDI `SP.POP.TOTL.{MA,FE}.IN` | `M`, `F` |
| `education_band` | enum | no | WDI `SE.SEC.CUAT.LO.ZS` | `PRIMARY_OR_LESS`, `SECONDARY_OR_MORE` |
| `urban_rural` | enum | no | WDI `SP.URB.TOTL.IN.ZS` | `URBAN`, `RURAL` |
| `occupation_group` | enum | **yes** | ILO sector shares | Null when not employed |
| `employment_status` | enum | no | ILO via WDI | `WAGE_WORKER`, `OWN_ACCOUNT`, `EMPLOYER`, `UNPAID_FAMILY`, `UNEMPLOYED`, `NOT_IN_LABOUR_FORCE` |
| `income_band` | enum | no | WDI `SI.DST.*` | `Q1`…`Q5`, per-capita household income quintile |
| `expected_monthly_income_vnd` | integer | no | derived | Quintile mean, VND |
| `income_is_own_earnings` | boolean | no | derived | False for people outside the labour force |
| `financial_access_segment` | enum | no | derived from Findex | `UNBANKED`, `TRANSACTIONAL`, `BASIC`, `FULL` |
| `digital_usage_segment` | enum | no | derived from Findex | `NONE`, `LOW`, `MEDIUM`, `HIGH` |
| `has_bank_account` | boolean | no | Findex `account.t.d` | |
| `uses_digital_payment` | boolean | no | Findex `g20.any` | Requires an account |
| `has_formal_saving` | boolean | no | Findex `fin17a.17a1.d` | Requires an account |
| `has_formal_borrowing` | boolean | no | Findex `borrow.any.t.d` | |
| `has_mobile_money` | boolean | no | Findex `mobileaccount.t.d` | Requires an account |
| `salary_paid_into_account` | boolean | no | Findex `fin32.n33.acc.s` | Wage workers only |
| `customer_tenure_band` | enum | no | assumption | `<1Y`, `1-3Y`, `3-5Y`, `5Y+` |
| `residency_status` | enum | no | generated | `RESIDENT` |

**No name, national ID, phone, address, or date of birth** — absent, not masked.

## `bank_view/businesses.csv` — 720 rows

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `business_id` | string | no | generated | Primary key |
| `business_kind` | enum | no | derived from ILO | `HOUSEHOLD_BUSINESS`, `REGISTERED_ENTERPRISE` |
| `legal_form` | enum | no | assumption | `SOLE_PROPRIETOR`, `LLC`, `JSC`, `PARTNERSHIP` |
| `industry_group` | enum | no | ILO sector shares | `AGRICULTURE`, `INDUSTRY`, `SERVICES` |
| `urban_rural` | enum | no | WDI | |
| `business_age_band` | enum | no | assumption | `<1Y`, `1-3Y`, `3-10Y`, `10Y+` |
| `employee_size_band` | enum | no | assumption (Pareto) | `0`, `1-9`, `10-49`, `50-199`, `200+` |
| `employee_count` | integer | no | assumption (Pareto) | 0 for household businesses |
| `revenue_band` | enum | no | derived | `<50M`…`20B+` VND per month |
| `expected_monthly_turnover_vnd` | integer | no | derived | |
| `cash_intensity_band` | enum | no | assumption | `LOW`, `MEDIUM`, `HIGH` |
| `digital_payment_intensity` | enum | no | derived | `LOW`, `MEDIUM`, `HIGH` |
| `domestic_international_profile` | enum | no | assumption | `DOMESTIC_ONLY`, `MIXED`, `INTERNATIONAL_HEAVY` |
| `has_bank_credit` | boolean | no | Enterprise Surveys `IC.FRM.BNKS.ZS` | |
| `uses_bank_working_capital` | boolean | no | `IC.FRM.BKWC.ZS` | |
| `has_female_ownership` | boolean | no | `IC.FRM.FEMO.ZS` | |

## `bank_view/accounts.csv` — 6,000 rows

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `account_id` | string | no | generated | Primary key |
| `owner_id` | string | no | generated | FK → `customers` or `businesses` |
| `owner_type` | enum | no | generated | `CUSTOMER`, `BUSINESS` |
| `account_type` | enum | no | derived | `CURRENT`, `SAVINGS`, `BUSINESS_CURRENT` |
| `currency` | enum | no | fixed | `VND` |
| `open_date` | date | no | generated | Before every transaction on the account |
| `status` | enum | no | generated | `ACTIVE` |
| `behavior_archetype` | enum | no | Phase 3 | One of five archetypes, or `SPARSE_ACTIVITY` |
| `expected_monthly_turnover_vnd` | integer | yes | Phase 8 | Calibration target |

## `bank_view/transactions.csv` — 461,537 rows

| Column | Type | Null | Source | Description |
|---|---|---|---|---|
| `transaction_id` | string | no | generated | Primary key |
| `event_id` | string | no | derived | SHA-256 prefix; Kafka dedup key, unique |
| `schema_version` | string | no | fixed | `1.0` |
| `timestamp` | timestamp | no | IBM date + redrawn time | |
| `source_account_id` | string | **yes** | IBM (mapped) | Null when the payer is external |
| `destination_account_id` | string | **yes** | IBM (mapped) | Null when the payee is external |
| `source_counterparty_token` | string | **yes** | generated | `CPY-*` when the payer is external |
| `destination_counterparty_token` | string | **yes** | generated | `CPY-*` when the payee is external |
| `amount` | integer | no | IBM × per-account scale | VND, always ≥ 1 |
| `currency` | enum | no | fixed | `VND` |
| `payment_format` | enum | no | **redrawn** | 8 Vietnamese instruments |
| `channel` | enum | no | derived | `MOBILE`, `INTERNET`, `ATM`, `BRANCH`, `POS`, `QR` |
| `transaction_type` | enum | no | derived | `TRANSFER`, `DEPOSIT`, `WITHDRAWAL`, `PURCHASE`, `SALARY`, `FEE` |
| `merchant_id` | string | **yes** | generated | FK → `merchants`, for card and QR |
| `time_partition` | enum | no | derived | `EARLY`, `MIDDLE`, `LATE` within the window |

**Endpoint rule:** exactly one of `*_account_id` / `*_counterparty_token` is
populated per side. Validated on every row.

**`payment_format` is not IBM's.** IBM's predicted its own laundering label at
7.2× lift, so it was redrawn from a Vietnamese taxonomy conditioned on the
customer's digital segment, direction, and size — never on the label.

## `bank_view/devices.csv` — 5,157 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `device_id` | string | no | Primary key |
| `customer_id` | string | no | FK → `customers`; the registering owner |
| `device_type` | enum | no | `ANDROID`, `IOS`, `WEB` |
| `first_seen` / `last_seen` | timestamp | no | Observation window bounds |

## `bank_view/merchants.csv` — 354 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `merchant_id` | string | no | Primary key |
| `merchant_category` | enum | no | 10 categories, conditioned on operator industry |
| `urban_rural` | enum | no | Inherited from the operating business |
| `operated_by_business_id` | string | yes | FK → `businesses` |

## `bank_view/relationships.csv` — 12,547 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `relationship_id` | string | no | Primary key |
| `source_entity_id` / `destination_entity_id` | string | no | Any entity id |
| `source_entity_type` / `destination_entity_type` | enum | no | `CUSTOMER`, `BUSINESS`, `ACCOUNT`, `DEVICE`, `MERCHANT` |
| `relationship_type` | enum | no | `OWNS`, `USES_DEVICE`, `SHARES_DEVICE`, `BUSINESS_OWNER` |
| `valid_from` | timestamp | no | |
| `valid_to` | timestamp | **yes** | Null means currently valid |

---

# Ground Truth

**Never a model input.** Join after features are computed, for evaluation only.

## `ground_truth/entity_labels.csv` — 7,773 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `entity_id` | string | no | `ACC-*`, `CUS-*`, or `BIZ-*` |
| `entity_type` | enum | no | `ACCOUNT`, `CUSTOMER`, `BUSINESS` |
| `label_type` | enum | no | `IBM_AML_INVOLVEMENT` |
| `label_value` | integer | no | `1` involved, `0` not |
| `active_from` / `active_to` | timestamp | no | Validity interval |
| `source` | enum | no | `IBM_AML` |

Involvement is deliberately broad: touched by at least one flagged transaction,
either endpoint.

## `ground_truth/transaction_labels.csv` — 461,537 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `transaction_id` | string | no | FK → Bank View transactions |
| `is_laundering` | integer | no | `1` / `0`, IBM's label |
| `scenario_id` | string | **yes** | FK → `scenario_instances`; set for 1,235 rows |
| `scenario_stage` | enum | **yes** | `PLACEMENT`, `LAYERING`, `INTEGRATION` |
| `source` | enum | no | `IBM_AML`, `IBM_PATTERNS`, `P022_SIMULATION` |

## `ground_truth/scenario_instances.csv` — 150 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `scenario_id` | string | no | Primary key |
| `network_id` | string | no | FK → `criminal_networks` |
| `typology` | enum | no | `STACK`, `CYCLE`, `FAN-IN`, `FAN-OUT`, `SCATTER-GATHER`, `GATHER-SCATTER`, `BIPARTITE`, `RANDOM` — IBM's own names |
| `typology_parameter` | string | yes | e.g. `Max 12 hops` |
| `transaction_count` / `account_count` | integer | no | |
| `first_event` / `last_event` | timestamp | no | Source clock |
| `split` | enum | no | The one split this instance belongs to |
| `benchmark_quota` | boolean | no | Always `true` |
| `prevalence_claim` | boolean | no | Always `false` |
| `source` | enum | no | `IBM_PATTERNS` |

## `ground_truth/criminal_networks.csv` — 1,451 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `network_id` / `scenario_id` | string | no | |
| `member_entity_id` | string | no | `ACC-*` |
| `member_entity_type` | enum | no | `ACCOUNT` |
| `owner_entity_id` / `owner_entity_type` | string / enum | no | The account's owner |
| `true_role` | enum | no | `ORIGINATOR`, `PASSTHROUGH`, `BENEFICIARY`, `ISOLATED` — structural position, not culpability |
| `source` | enum | no | `IBM_PATTERNS` |

## `ground_truth/hard_negative_instances.csv` — 225 rows

| Column | Type | Null | Description |
|---|---|---|---|
| `hard_negative_id` | string | no | Primary key |
| `family` | enum | no | Six families |
| `entity_id` / `entity_type` / `account_id` | string | no | |
| `transaction_count` | integer | no | |
| `legitimate_explanation` | string | no | Why this is not laundering |
| `observable_collision` | string | no | Which rule it trips |
| `ground_truth` | enum | no | Always `LEGITIMATE` |
| `split` | enum | no | |
| `source` | enum | no | `P022_SIMULATION` |

---

# Splits

`splits/{train,validation,test,hidden_test}_entities.csv`

| Column | Type | Null | Description |
|---|---|---|---|
| `entity_id` | string | no | `CUS-*` or `BIZ-*` |
| `entity_type` | enum | no | `CUSTOMER`, `BUSINESS` |
| `split` | enum | no | Redundant with the filename, deliberately |

Accounts and devices inherit their owner's split. Every criminal network sits
entirely in one split — verified, 0 crossings.

---

# `manifest.json`

Dataset identity, seed, git commit, IBM source checksum, public source ids,
subgraph selection statistics, row counts, the full assumption register, gate
verdicts, `prevalence_claim: false`, `known_limitations`, and SHA-256 plus row
count for all 20 files.
