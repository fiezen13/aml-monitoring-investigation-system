# Monetary calibration

Phase 8. How IBM's monetary scale becomes Vietnamese dong.

## What is deliberately not done

An FX multiplication. IBM's amounts span fifteen currencies and eighteen orders
of magnitude in a synthetic world with no Vietnamese content; multiplying by a
dong rate would produce numbers that look Vietnamese and mean nothing. Its
maximum single transaction is 8.16 trillion units and its minimum is 0.000001.

## What IBM actually contributes

**Relative structure.** How large a payment is against that account's own
typical payment. How much flows in against how much flows out. How turnover
compares to a single transaction. Those ratios are dimensionless, they are what
the archetypes are built from, and they are the part worth keeping.

## Method

One multiplicative scale factor per account:

```text
scale = target monthly inflow in VND / observed IBM monthly inflow
```

Every transaction on that account is multiplied by its account's scale.

Because the scale is constant within an account, **every within-account ratio is
preserved exactly** — fan patterns, inflow-to-outflow balance, turnover multiple,
and the relative size and ordering of individual payments. Only the unit changes.
This is asserted in `verify_ratio_preservation` and checked on a sample of
matched accounts in every run.

The observed inflow covers the source's 27.67-day window and is converted to a
30-day month before comparison. Skipping that would bias every amount in the
release by about 8% — small enough to pass a glance, large enough to matter.

### Target inflow

For an individual:

```text
target = expected monthly income
       x ASSUME_HOUSEHOLD_INCOME_RATIO     (GDP per capita is not household income)
       x ASSUME_INCOME_TO_TURNOVER         (money crossing the account vs income)
```

For a business:

```text
target = expected monthly turnover x ASSUME_BUSINESS_TURNOVER_TO_INFLOW
```

Businesses use turnover, never individual income bands. A household trader
turning over thirty million dong a month and a wage worker earning thirty million
are different animals; giving them the same distribution would make every
turnover-based AML feature meaningless.

## The assumptions, and why they are assumptions

| ID | Value | Range | Why not evidenced |
|---|---:|---|---|
| `ASSUME_INCOME_TO_TURNOVER` | 1.6 | 1.0 – 3.0 | **No acquired source links declared income to money crossing an account.** This is the hinge of the entire monetary scale. |
| `ASSUME_HOUSEHOLD_INCOME_RATIO` | 0.62 | 0.45 – 0.80 | GDP per capita is the only VND-denominated anchor acquired. It includes corporate and government value added and divides by everyone, not by earners. |
| `ASSUME_BUSINESS_TURNOVER_TO_INFLOW` | 0.85 | 0.6 – 1.2 | Not published. Cash-intensive firms bank less of their turnover. |

All three are `confidence: low`. The release should be generated at several
settings so the sensitivity is measured rather than asserted — none of these is
a number anyone should defend to three significant figures.

## Realized results

5,800 matched accounts; **5,776 calibrated (99.6%)**.

| | Monthly inflow (VND) |
|---|---:|
| Minimum | 3,554,209 |
| Median | 8,415,112 |
| p95 | 30,768,845 |
| Maximum | 6,892,221,279 |

A median of about 8.4 million dong a month for an individual account is
plausible for Vietnam. The maximum belongs to a large business.

**Scale factors span 7.35 orders of magnitude.** That is expected, not a defect:
IBM denominates accounts in fifteen currencies, so an account measured in Bitcoin
and one measured in Yen need wildly different multipliers to reach the same dong
figure. It is the clearest possible demonstration of why absolute IBM amounts are
never used directly.

The 24 uncalibrated accounts (0.4%) are IBM accounts with genuinely zero
observed inflow — pure senders. They carry `scale_factor: null` and an explicit
`uncalibrated_reason` rather than a fabricated default, because a substituted
value would be invisible downstream.

## A correction made during development

An earlier version assigned expected income only to employed customers, leaving
27% of the population — everyone outside the labour force — with no basis for
calibration. That was wrong twice over: income quintiles are *per-capita
household* income, which everyone has, and Findex shows 41.3% of adults outside
the labour force hold an account. Those accounts are funded by something.
Expected income is now assigned to every customer, with `income_is_own_earnings`
recording whether it is money they earn or money accruing to them. Uncalibrated
accounts fell from 1,349 to 24.
