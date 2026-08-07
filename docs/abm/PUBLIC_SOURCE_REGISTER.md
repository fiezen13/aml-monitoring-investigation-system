# ABM-BANK public source register

Status: Phase 2 proposed register

Machine-readable source: `abm/sources/source_registry.yaml`

Registry version: 0.1.0

Reviewed: 2026-08-07

## Evidence policy

A source's presence in this register permits only the uses listed on its source card. It does not make the source representative of Viet Nam, a commercial bank, or real AML incidence.

The traceability chain for every future parameter is:

```text
source ID + immutable version/checksum
  -> machine-readable source profile
  -> derived statistic with code/version
  -> parameter card
  -> generator component
  -> release manifest
```

No source records from unrelated populations will be joined as if they describe the same person. Harmonization will use conditional distributions, weighted margins, statistical matching, or calibrated assumptions.

## Registered sources

### SRC_IBM_AML_DATA_2023 — IBM AML transaction data

Reference: [IBM AML-Data repository](https://github.com/IBM/AML-Data)

What can be learned:

- a large synthetic bank-transaction file shape already supported by P-022;
- payment formats, currency-pair representation, timestamps, and directed account flows;
- scale/performance characteristics for profiling and ingestion;
- sensitivity baselines for amount, temporal, and graph statistics.

What must not be inferred:

- Vietnamese customer demographics or channel share;
- real bank behavior or AML prevalence;
- scenario quotas;
- any row-level identity shared with another source.

IBM states that the repository is Apache-2.0 and the released data is CDLA-Sharing-1.0. The downloaded variant, checksum, and terms must be captured before profiling. IBM describes the data as a multi-agent synthetic world, not anonymized real customers.

### SRC_IBM_AMLSIM_2021 — AMLSim

Reference: [IBM AMLSim](https://github.com/IBM/AMLSim)

What can be learned:

- configuration and simulator-module architecture;
- reproducible graph-generation and pattern-injection methods;
- scale-test methodology for graph/ML benchmarks;
- useful failure modes of default-heavy synthetic generators.

What must not be inferred:

- Vietnamese population, bank products, or transaction distributions;
- true laundering frequency;
- that AMLSim defaults are evidence-backed ABM-BANK parameters;
- that copied AMLSim output is a new ABM-BANK world.

The project recommends its master branch and warns that other branches and some wiki material are outdated. Direct code reuse is optional; architectural comparison is the primary use.

### SRC_SYNTHAML_2023 — SynthAML

References: [Scientific Data descriptor](https://doi.org/10.1038/s41597-023-02569-2), [Figshare data collection](https://doi.org/10.6084/m9.figshare.c.6504421.v1)

What can be learned:

- transaction histories relative to alert dates;
- temporal split and concept-drift evaluation methodology;
- transaction-type conditional behavior;
- conditional aggregation/copula methodology;
- realistic order-of-magnitude tests for large alert-history datasets.

What must not be inferred:

- raw monetary distributions, because amounts are logged and standardized;
- business behavior or graph structure;
- Vietnamese population behavior;
- real high-risk or alert-outcome proportions;
- AML prevalence.

The descriptor covers 20,000 alerts and more than 16 million transactions derived from a Danish bank's private-client alert population. The authors explicitly say the data were stratified, the approximately 17% reported-alert share is not real prevalence, and one validation setup has target leakage. Those warnings are binding for ABM-BANK.

### SRC_WB_GLOBAL_FINDEX_VNM_2024 — Global Findex Viet Nam

References: [World Bank Global Findex downloads](https://www.worldbank.org/en/publication/globalfindex/download-data), [Viet Nam 2024 microdata catalog](https://microdata.worldbank.org/catalog/7998)

What can be learned:

- national adult account ownership and digital-payment margins;
- differences by age, income group, labor-force status, gender, and urban/rural location;
- salary/government-payment participation and digital access;
- conditional constraints for population harmonization.

What must not be inferred:

- a particular bank's customer mix;
- number of accounts per customer;
- transaction amount, count, or inter-arrival distributions;
- business behavior or AML prevalence;
- population estimates from unweighted microdata counts.

Findex is representative of adults age 15+, not customers of one bank. A selection model is therefore required between national population margins and the ABM bank portfolio.

### SRC_VN_NSO_LFS_2024 — Viet Nam Labour Force Survey

Reference: [National Statistics Office employment portal](https://www.gso.gov.vn/en/employment/)

What can be learned:

- age, employment, occupation, industry, residence, province, and income margins;
- conditional structure for individual agents;
- salary-agent and employment relationship populations.

What must not be inferred:

- bank customer selection without a separate model;
- person-level Findex linkage;
- bank-declared income or account turnover directly from worker income;
- transaction behavior or AML prevalence.

Future profiling must record the exact Labour Force Survey table, classification version, weights, unit, publication file, and checksum.

### SRC_VN_NSO_ENTERPRISES_2024 — Viet Nam enterprise statistics

References: [National Statistics Office enterprise tables](https://www.gso.gov.vn/en/enterprises/), [Statistical Yearbook portal](https://www.gso.gov.vn/en/statistic-book/)

What can be learned:

- enterprise counts by industry, province, legal type, and employee size;
- employee, capital, turnover, and compensation margins;
- proportions for enterprise, household-business, employer, and merchant archetypes;
- macro constraints for legitimate high-volume business hard negatives.

What must not be inferred:

- daily bank transactions;
- beneficial ownership networks;
- exact SME composition at one bank;
- person-level links to household surveys;
- AML prevalence.

Coverage must be kept explicit: acting enterprises, enterprises with reported business outcomes, and non-farm individual establishments are different denominators and cannot be concatenated.

### SRC_SBV_ANNUAL_REPORT_2023 — State Bank of Viet Nam annual report

Reference: [State Bank of Viet Nam Annual Report 2023](https://www.sbv.gov.vn/documents/d/sbv_portal/590044)

What can be learned:

- supported payment rails and official terminology;
- macro counts/values and digital-payment trends;
- high-level consistency bounds for channel and payment-system scale.

What must not be inferred:

- individual transaction frequencies or amounts;
- customer demographics or account ownership;
- a single bank's market share;
- intraday/weekday behavior;
- AML prevalence or scenario quotas.

Annual aggregate totals can constrain a simulation, but they do not identify a micro-level distribution. Every used table needs unit and coverage notes.

### SRC_FATF_PML_2018 — FATF Professional Money Laundering

Reference: [FATF Professional Money Laundering report](https://www.fatf-gafi.org/en/publications/Methodsandtrends/Professional-money-laundering.html)

What can be learned:

- coordinator, mule, proxy, cash-controller, and service-provider roles;
- network preconditions and stage ordering;
- account-management, proxy-network, and layering mechanisms;
- causal acceptance criteria for scenario modules.

What must not be inferred:

- amounts, actor counts, delays, or prevalence;
- Vietnamese population parameters;
- that a qualitative red flag proves criminality.

This is authoritative typology evidence but a selected cross-jurisdictional case collection, not a probability sample.

### SRC_FINCEN_FUNNEL_2014 — Funnel accounts and TBML

Reference: [FinCEN Advisory FIN-2014-A005](https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2014-a005)

What can be learned:

- fan-in deposits, consolidation, rapid outbound movement, and geographic mismatch;
- scenario ordering and observable evidence combinations;
- required legitimate controls and hard negatives.

What must not be inferred:

- use of the US USD 10,000 threshold in Viet Nam;
- exact counts, amounts, or dwell times;
- AML prevalence;
- automatic criminal labels from a single indicator.

FinCEN explicitly says the indicators may be legitimate and must be evaluated with expected customer activity and other information. ABM-BANK scenarios must preserve that ambiguity.

### SRC_ELLIPTIC_2019 — Elliptic Bitcoin graph

References: [Elliptic dataset](https://www.kaggle.com/datasets/ellipticco/elliptic-data-set), [dataset paper](https://arxiv.org/abs/1908.02591)

What can be learned:

- implementation and validation of directed temporal graph profiling;
- degree, component, and neighborhood statistics;
- temporal graph split and scale methodology.

What must not be inferred:

- bank-account degree or component targets;
- Vietnamese fiat payment behavior;
- transaction amount distributions;
- AML prevalence;
- opaque features as Bank View fields.

The released graph has 203,769 transaction nodes, 234,355 edges, and many unknown labels. Bitcoin UTXO mechanics are not bank-account mechanics. The CC BY-NC-ND 4.0 license also requires legal review before any derivative or commercial use.

## Source selection gaps

The registry intentionally does not yet claim strong sources for:

- account count per customer in a Vietnamese commercial bank;
- device count and digital-session behavior;
- customer-to-bank selection and product mix;
- transaction amount/inter-arrival distributions by Vietnamese customer segment;
- merchant MCC and purchase behavior;
- mule dwell time and scenario numeric parameters;
- beneficial ownership and legitimate relationship graph distributions.

These gaps must be resolved by protected aggregate bank calibration data, a stronger public source, or explicit low-confidence assumptions with sensitivity ranges. They must not become invisible Python constants.

## Phase-2 gate result

The Source Registry structure passes the documentation gate. It does not yet pass the future parameter-evidence gate because source files have not been downloaded, checksummed, or profiled, and no derived statistics exist. Phase 3 must make those artifacts reproducible before Phase 4 assigns values.
