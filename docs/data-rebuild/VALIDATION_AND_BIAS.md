# Validation and synthetic bias

Realized results for the 5,000-individual + 800-business preview.
Machine-readable: `artifacts/intermediate/kyc_preview/validation_report.json`.

## 1. Distribution validation — PASS

Every generated marginal compared against the published statistic it came from.

**Maximum absolute error across all checks: 0.0148** (1.5 percentage points), on
`employment_status = WAGE_WORKER` — source 33.44%, generated 34.92%, which is
sampling noise at n=5,000.

Financial behavior, the part that goes through the assumed logit-additive model:

| Behavior | Source | Generated | Δ |
|---|---:|---:|---:|
| Account ownership | 70.55% | 70.58% | +0.03 pt |
| Digital payment | 62.38% | 62.62% | +0.24 pt |
| Formal saving | 44.51% | 44.72% | +0.21 pt |
| Borrowed any money | 43.20% | 42.84% | −0.35 pt |
| Mobile money account | 38.72% | 38.79% | +0.07 pt |
| Salary into account (wage workers) | 80.88% | 81.14% | +0.26 pt |

All within a third of a percentage point.

## 2. Conditional structure — PASS

If attributes had been drawn independently, account ownership would be flat
across education and income. Published gradients are steep, so a flat result here
would mean the conditional structure had been lost.

| Attribute | Account ownership rate | Spread |
|---|---|---:|
| Education | Primary or less 33.4% → secondary or more 88.4% | 0.550 |
| Income | Q1 33.1% → Q2 46.6% → Q3 83.9% → Q4 91.7% → Q5 95.2% | 0.621 |
| Employment | Not in labour force 34.3% → employer 94.9% | 0.606 |
| Residence | Rural 55.6% → urban 92.9% | 0.374 |

The gradients are monotone and in the published direction.

## 3. Matching quality — PASS

0 accounts reused across 5,800 matches. Median score 0.9665, mean 0.9497. All
five archetypes used, by both entity types. Detail in
[KYC_GENERATION_AND_MATCHING.md](KYC_GENERATION_AND_MATCHING.md).

## 4. Label leakage — PASS

**This is the test that decides whether the dataset is usable for its purpose.**

The laundering label is a property of the matched IBM account and reaches the KYC
side only through the matcher. A strong association would mean the matcher is
routing a KYC attribute towards laundering-heavy behavior.

Base rate: **3.81%** (221 of 5,800 matched entities).

| Attribute | Value | n | Flagged | Lift |
|---|---|---:|---:|---:|
| employee_size_band | 1-9 | 37 | 5.41% | 1.42× |
| industry_group | INDUSTRY | 275 | 5.09% | 1.34× |
| employment_status | EMPLOYER | 59 | 5.08% | 1.33× |
| age_band | 25-34 | 941 | 4.89% | 1.28× |
| industry_group | AGRICULTURE | 189 | 4.76% | 1.25× |
| age_band | 35-44 | 1,051 | 4.76% | 1.25× |
| cash_intensity_band | LOW | 151 | 4.64% | 1.22× |

- **No perfect predictors.** No attribute value has a 0% or 100% flagged rate.
- **Maximum lift 1.42×**, well below the 3× threshold, and on a 37-entity cell
  where that is noise.
- **Mutual information at most 0.0036 bits** — `cash_intensity_band`, the
  highest. `education_band`, `digital_usage_segment`, and `customer_tenure_band`
  are exactly 0.0.

Lift catches one category behaving unusually; mutual information catches an
attribute carrying information spread thinly across many categories, which lift
would miss. Both are near zero.

The 6.67× lift carried by `MULTI_CURRENCY_SELF_CYCLING` does **not** propagate to
KYC attributes, because archetype assignment is sampled softly and only 4.2% of
entities land there.

> Caveat worth stating: this measures the association that exists *now*, before
> AML scenarios are injected and before hard negatives are added. Phase 14 must
> re-run it on the finished release. Passing here is necessary, not sufficient.

## 5. Calibration — PASS

99.6% calibrated; within-account ratios preserved on every sampled account. See
[MONETARY_CALIBRATION.md](MONETARY_CALIBRATION.md).

---

# Potential sources of synthetic bias

Stated because they are real, not because they are fixable today.

## From the IBM backbone

**The population is businesses, not individuals.** IBM holds 3,017 individual
accounts against 2.07 million business accounts. Every synthetic Vietnamese
retail customer is matched to behavior that a Partnership, Corporation, or Sole
Proprietorship actually produced. Retail transaction patterns in this dataset are
business patterns with a retail label. This is the largest single bias in the
pipeline.

**No daily rhythm.** IBM assigns times uniformly at random — every hour from
01:00 to 23:00 holds 3.88–3.90% of transactions. Night-activity and
business-hours features will be noise unless timestamps are redrawn.

**A four-week window.** 27.67 days cannot support monthly seasonality, a 90-day
baseline, or a meaningful chronological split.

**Payment format is an injector signature.** 87% of laundering rows are ACH;
Wire and Reinvestment contain none. Carrying it across unchanged would leak.

**Currency spread is partly a label signature**, for the same reason — the CYCLE
typology hops currencies. It remains a clustering feature because it is also
genuinely behavioral, but that is a defensible choice rather than an obvious one.

## From the Vietnamese sources

**No sub-national structure.** The acquired API is national only. Every
synthetic customer's region is undefined, and urban/rural is drawn independently
of everything else. Real Vietnamese financial behavior varies sharply between the
Red River Delta, the Central Highlands, and the Mekong Delta.

**Age is independent of employment and income.** No acquired source
cross-tabulates them. In reality the young and the old are far less likely to be
employed, and income peaks in middle age. The generated population has 65+
customers as likely to be wage workers as 35-44 customers — which is wrong, and
will make any age-based behavioral feature weaker than it should be.

**Interaction effects are understated.** The logit-additive model treats
disadvantages as additive in log-odds. Real exclusion compounds: a rural woman
with primary education in the poorest quintile is likely worse off than the sum
of those four effects. The synthetic population's tail of exclusion is therefore
too thin.

**Three-sector occupation only.** Agriculture, industry, services is all the
source publishes. Any feature depending on finer occupation will not work.

**The income anchor overstates.** GDP per capita includes corporate and
government value added and divides by everyone, not by earners. It is corrected
by an assumption (0.62) with a wide range, not by a measurement.

**Education mapping is approximate.** WDI "at least lower secondary attainment"
is treated as Findex "secondary education or more". The definitions are close but
not identical, and education is the strongest conditional in the model — so an
error here propagates further than an error anywhere else.

## From the business model

**Firm size is a cross-country regularity, not Vietnam.** The Pareto shape is
assumed. Vietnam's actual firm size distribution is not in any acquired source.

**Industry mix over-weights industry.** Employment shares are used as
establishment shares, and a factory employs more people than a shop.

**Household businesses are thinly evidenced.** They are 95.4% of the business
population by the derived split, and they are exactly where Enterprise Surveys
has no coverage and where cash intensity concentrates — the segment that matters
most for AML realism is the one with the least data behind it.

## From the matching

**`ASSUME_EXPECTED_BEHAVIOR_MAPPING` is the largest judgement in the pipeline.**
Every value mapping KYC attributes to expected behavior is a modelling opinion.
If those opinions are wrong, the entire join is wrong in a way no internal
validation can detect — the marginals would still match, the gradients would
still be steep, and the leakage test would still pass.

**Soft sampling trades sharpness for safety.** A lower temperature would produce
better-fitting matches and more KYC–label association. 1.35 is a choice on that
trade-off, not an optimum.

**Only 20,000 candidate accounts per archetype are loaded**, deterministically
ordered by account key. Fine at this scale, but a larger release should sample
the pool rather than take a prefix, or it will over-represent whatever the key
ordering happens to correlate with.
