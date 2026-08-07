# KYC generation and statistical matching

Phases 6, 7, and 9. How the synthetic Vietnamese population is generated and
joined to IBM behavior.

```bash
python -m abm.cli generate-kyc --individuals 5000 --businesses 800
```

Outputs (gitignored): `artifacts/intermediate/kyc_preview/` — `customers.csv`,
`businesses.csv`, `matched_accounts.csv`, `account_lineage.csv`,
`pipeline_summary.json`, `validation_report.json`.

## Phase 6 — individuals

Attributes are generated **conditionally, in dependency order**, never as
independent draws:

```text
education, employment, residence, income   (jointly, via IPF)
    -> age band and sex                    (independent; no source links them)
    -> occupation                          (conditional on being employed)
    -> account access                      (conditional on all of the above)
    -> digital use, saving, borrowing      (gated on having an account)
```

### The joint block

Sources publish *margins* — 33.4% of adults are wage workers, each income
quintile holds 20% — but never the *joint*. Two bad options present themselves:
treat the dimensions as independent, which makes an employer as likely to be poor
as a family worker is to be rich; or write the joint by hand, which produces
plausible numbers whose margins match no published statistic.

Iterative proportional fitting gives a third. A seed matrix encodes the *shape*
of the association; rows and columns are then scaled alternately until the
margins match the published ones exactly. **The evidence constrains the margins,
the assumption supplies the association, and the two stay separable** — so the
assumption can be varied in a sensitivity test without disturbing the evidence.
At `strength = 0` it reproduces independence exactly, which keeps the honest null
reachable.

### No real people, and no realistic identifiers

No name, no national ID, no phone number, no address, no date of birth — not
hashed, not masked, **absent**. Every attribute is a band.

A synthetic CCCD number would be worse than useless: it looks like a real
identifier, so it invites being treated as one, while carrying no information a
band does not. A test asserts none of these fields exists.

No AML, risk, or suspicion field is generated either. A KYC field that implies
AML would make Phase 14 unfalsifiable.

## Phase 7 — businesses

Modelled separately throughout. Individual income distributions are never reused
for business revenue.

**Derived, not assumed:** the split between household businesses and registered
enterprises comes from the own-account to employer ratio in employment. A
business entity in a bank's book is operated by one or the other, so their ratio
in the labour force is the population split — 95.4% household, 4.6% registered.

**From Enterprise Surveys 2023:** 29.2% of firms hold bank credit, 38.7% finance
working capital through banks, 24.8% have female participation in ownership.

**Assumed:** firm size (Pareto, a cross-country regularity rather than a
Vietnamese measurement), turnover as a multiple of value added, legal form within
registered enterprises, and cash intensity by industry. Industry mix is derived
from employment by sector, which over-weights industry because a factory employs
more people than a shop — recorded as `ASSUME_INDUSTRY_FROM_EMPLOYMENT`.

## Phase 9 — statistical matching

**No claim of identity is made.** An IBM account is not asserted to *be* a
Vietnamese person. A synthetic KYC agent is generated first, its expected
behavior is derived from its own attributes, and it is then paired with an IBM
account whose observed behavior is compatible. What transfers is the shape of the
activity; nothing transfers about who anyone is.

### Two transparent stages

Deliberately no learned embedding and no neural matcher — nothing whose failure
would be invisible.

**1. Archetype propensity.** Each agent's attributes imply expectations on five
scale-free dimensions: flow direction, counterparty breadth, activity rhythm,
international exposure, instrument concentration. Those are scored against each
archetype's centroid, softmaxed, and **sampled**.

Sampling rather than taking the best match is essential. An argmax would collapse
every agent with identical attributes onto one archetype and destroy the
within-segment variation that makes a dataset worth modelling.

**2. Rank matching within the archetype.** Entities and accounts are both ordered
by expected turnover and paired in rank order, so the poorest customer in a group
gets the lowest-turnover account and the richest gets the highest. Each account is
used once.

This replaced a greedy nearest-neighbour search. Greedy is fine while a pool is
mostly empty and quadratic once it fills — the outward scan has to step over
every account already taken — and at the full release's two million entities it
does not finish. Rank matching is O(n log n), and for a monotone distance it is
also the *optimal* assignment where greedy is only an approximation.

Randomness is preserved by jittering each entity's target before sorting, so
identical entities still land on different accounts.

If an archetype runs out of accounts, the entity falls back to its
next-most-compatible archetype rather than being dropped or given a reused one.

### Lineage stays out of the release

The match records `ibm_behavior_source_account_hash`, a 16-character SHA-256
prefix — never the IBM account key. A test asserts the source key does not appear
in the hash. Canonical IDs are `ACC-00000001` onward, and the mapping lives only
in a gitignored intermediate artifact.

### The leakage this had to avoid

`MULTI_CURRENCY_SELF_CYCLING` carries **6.67× the population's rate** of
laundering-involved accounts, because IBM's CYCLE typology hops between
currencies.

If archetype assignment were driven by anything resembling a risk judgement —
routing high-income or internationally active customers there — then income and
international exposure would predict the AML label before a single scenario was
generated, and Phase 14 would be unfalsifiable.

Two defences: propensity uses only behavioral expectations and never any field
derived from the label; and `ASSUME_ARCHETYPE_TEMPERATURE` (1.35) keeps sampling
soft so every archetype draws a broad mix of KYC attributes. The residual
association is measured after matching, not assumed away.

## Realized matching quality

5,000 individuals + 800 businesses = 5,800 matches.

| Metric | Value |
|---|---|
| Accounts reused | **0** |
| Matching score — median | see release report |
| Archetypes used | 5 of 5 |

Score is `1 / (1 + distance)` on the standardized turnover axis, so 1.0 is exact.

| Archetype | All | Individuals | Businesses |
|---|---:|---:|---:|
| INBOUND | 2,848 | 2,601 | 247 |
| OUTBOUND_BURSTY | 1,313 | 1,095 | 218 |
| SPORADIC_SELF_CYCLING | 1,097 | 928 | 169 |
| WIDE_FAN_IN_SINGLE_INSTRUMENT | 300 | 192 | 108 |
| MULTI_CURRENCY_SELF_CYCLING | 242 | 184 | 58 |

Both entity types spread across all five archetypes rather than segregating,
which is what soft sampling is for. Businesses are over-represented in
`WIDE_FAN_IN_SINGLE_INSTRUMENT` (13.5% against 5.2% of individuals), which is the
expected direction — that archetype receives from many parties.

Only 4.2% of entities land in the leaky archetype, which limits how much of its
6.67× lift can reach any KYC attribute.

## Assumptions introduced in these phases

| ID | Confidence | Note |
|---|---|---|
| `ASSUME_INCOME_ASSOCIATION` (0.45) | low | Association strength across education, employment, residence, income. IPF keeps all four margins exact regardless. |
| `ASSUME_ECONOMIC_RANK` | low | Ordering of employment statuses by economic security. |
| `ASSUME_TENURE_DISTRIBUTION` | low | Banking tenure; no acquired source covers it. |
| `ASSUME_AGE_INDEPENDENCE` | low | Age drawn independently of employment and income. Known to be wrong. |
| `ASSUME_EDUCATION_MAPPING` | medium | WDI "at least lower secondary" treated as Findex "secondary or more". |
| `ASSUME_FIRM_SIZE_PARETO` (1.06) | low | Cross-country regularity, not a Vietnamese measurement. |
| `ASSUME_TURNOVER_TO_VALUE_ADDED` (2.5) | low | Turnover is not published; value added is. |
| `ASSUME_REGISTERED_LEGAL_FORM` | low | Needs NSO enterprise tables. |
| `ASSUME_CASH_INTENSITY_BY_INDUSTRY` | low | SBV publishes system aggregates, not by industry. |
| `ASSUME_INDUSTRY_FROM_EMPLOYMENT` | low | Employment shares used as establishment shares. |
| `ASSUME_ARCHETYPE_TEMPERATURE` (1.35) | low | Lower sharpens matching but increases KYC–label association. |
| `ASSUME_EXPECTED_BEHAVIOR_MAPPING` | low | **The largest judgement in the pipeline.** No acquired source relates Vietnamese customer attributes to transaction behavior. |

The last one deserves emphasis. Every number in `expected_behavior_vector` — that
a wage worker receives from one employer and pays out to many, that an
own-account trader receives from many customers — is a modelling judgement, not a
measurement. They are collected in one function so they can be argued with rather
than hunted for, and they are the first thing that should be replaced if
aggregate behavioral data from a Vietnamese bank ever becomes available.
