# Vietnam source profiling

Phases 4 and 5. 152 indicators acquired from the World Bank open data API,
cached, and turned into the conditional distributions the KYC generator runs on.

```bash
python -m abm.cli profile-sources
```

- Raw responses: `data/raw/worldbank/` — 164 files, gitignored, checksummed
- Acquisition record: `artifacts/source_profiles/vn_worldbank_acquisition.json`
- **Derived distributions: `data/source_registry/distributions/vn_population.yaml`** — tracked in Git

## The rule this phase enforces

No percentage is typed into Python. Every number that shapes the synthetic
population arrives through code, from a named indicator, with the response kept
on disk, so a reviewer can re-fetch it and get the same value.

That is why 12 of the 164 requested indicators are recorded as *unavailable*
rather than dropped: a later reader needs to tell "not requested" from
"requested and not published".

## What was acquired

| Group | Indicators | Vintage |
|---|---:|---|
| Global Findex (source 28), 7 behaviors × 13 breakdowns | 91 | 2024 |
| WDI population five-year bands | 28 | 2025 |
| WDI labour, income, education, macro | 29 | 2022–2025 |
| Enterprise Surveys | 4 | 2023 |
| **Total acquired** | **152** | |
| Unavailable | 12 | breakdowns of `fin32.n33.acc.s`, which Findex publishes only at headline level |

## Distributions actually used

### Population structure — all direct from source

**P(age_band)**, adults 15+, from `SP.POP.<band>.{MA,FE}.5Y` reweighted by sex
population counts:

| 15-24 | 25-34 | 35-44 | 45-54 | 55-64 | 65+ |
|---:|---:|---:|---:|---:|---:|
| 17.85% | 18.67% | 21.18% | 16.45% | 13.54% | 12.31% |

**P(gender)** — M 48.98%, F 51.02%.
**P(urban_rural)** — Urban 38.83%, Rural 61.17%.
**P(education_band)** — Secondary or more 65.97%, Primary or less 34.03%.

**P(employment_status)**, built in stages because participation, unemployment,
and the status split have three different denominators:

| Wage worker | Own account | Employer | Unpaid family | Unemployed | Not in labour force |
|---:|---:|---:|---:|---:|---:|
| 33.44% | 28.24% | 1.40% | 8.59% | 1.11% | 27.22% |

**P(occupation_group | employed)** — Agriculture 25.04%, Industry 34.83%,
Services 40.13%. Three sectors is all the source publishes.

**Income quintiles**, from income shares anchored on GDP per capita in VND:

| Quintile | Income share | Mean monthly income |
|---|---:|---:|
| Q1 | 6.8% | 3,582,872 ₫ |
| Q2 | 11.8% | 6,217,337 ₫ |
| Q3 | 16.1% | 8,482,976 ₫ |
| Q4 | 22.0% | 11,591,645 ₫ |
| Q5 | 43.2% | 22,761,775 ₫ |

Gini 36.1.

### Financial behavior — Findex 2024

| Behavior | Rate |
|---|---:|
| Account ownership | 70.6% |
| Made or received a digital payment | 62.4% |
| Formal saving | 44.5% |
| Borrowed any money | 43.2% |
| Mobile money account | 38.7% |
| Wages into an account (of wage recipients) | 80.9% |
| Mobile phone ownership | 97.8% |

Each is published broken down by sex, age, education, income group, urban/rural,
and labour-force status. Log-odds shifts for account ownership:

| Dimension | Shift |
|---|---|
| Education | Primary or less **−1.56**, secondary or more +0.24 |
| Labour force | Out **−1.22**, in +0.39 |
| Income group | Poorest 40% **−0.95**, richest 60% +0.90 |
| Urban/rural | Rural −0.15, urban +0.34 |
| Age | 15-24 +0.08, 25+ −0.02 |
| Sex | F −0.03, M +0.03 |

Education is by far the strongest signal, which is why `education_band` was
added to the KYC schema after the source data was examined. Sex barely matters.

## Combining breakdowns: the one assumption

Findex publishes each behavior **one dimension at a time**. There is a rate for
women, a rate for rural adults, a rate for the poorest 40% — but no rate for
*rural women in the poorest 40%*. The joint is not published and cannot be
recovered from the margins.

Combining them therefore requires an assumption, registered as
`ASSUME_LOGIT_ADDITIVITY`: each dimension contributes an independent additive
shift in log-odds. It is the standard method and it is transparently
falsifiable, but it is an assumption, not evidence.

**Interaction effects are the known casualty.** Real financial exclusion
concentrates where disadvantages compound — a rural woman with primary education
in the poorest quintile is likely worse off than the sum of those four effects.
An additive-in-log-odds model understates that by construction.

### Two corrections that turned out to be necessary

Both were found by checking generated output against source marginals rather
than by reasoning, and both were silent errors of several percentage points.

**Centering.** The logit is non-linear, so the log-odds of the overall rate is
not the population-weighted average of the per-category log-odds. Education
alone: 34% of adults at −1.56 and 66% at +0.24 gives a weighted mean of −0.37,
not zero. Summing six such dimensions subtracted about a full unit of log-odds
from the average customer and produced an account-ownership rate near 62%
against a published 70.6%. Each dimension's shifts are now re-centered on the
population.

**Intercept calibration.** Centering is necessary but not sufficient. The mean
*probability* is not the probability at the mean shift, because the logistic
curve is concave above 0.5 — and the correlations IPF deliberately introduces
widen the spread of shifts and push the two further apart. The residual error was
still about six points. The intercept is now solved by bisection so the
population mean probability hits the published rate exactly, leaving every
relative gradient untouched.

## What is not available and stays unresolved

| Missing | Consequence |
|---|---|
| Sub-national region | The KYC population has no regional structure. `P(region)` and `P(urban_rural \| region)` need the National Statistics Office. |
| `P(employment_status \| age_band)` | Age is drawn independently of employment. Known to be wrong in reality. |
| Occupation finer than three sectors | `P(occupation_group \| age_band, region)` is unsupported. |
| Declared KYC income vs survey income | No source links them. |
| Household income vs GDP per capita | The anchor overstates by an unmeasured factor, corrected by an assumption. |
| Firm size and turnover distributions | Enterprise Surveys does not publish them; a Pareto shape is assumed. |

Each is recorded in `unresolved:` in the source registry, and the affected
parameters carry `confidence: low`.

## Provenance chain

```text
World Bank API response  ->  data/raw/worldbank/<indicator>.json  (cached, checksummed)
                         ->  artifacts/source_profiles/vn_worldbank_acquisition.json
                         ->  data/source_registry/distributions/vn_population.yaml  (tracked)
                         ->  abm/kyc/individuals.py, abm/kyc/businesses.py
```

Every distribution in the YAML carries its `source_indicators`, its
`reference_year`, and whether it is `direct` or `logit_additive`.
