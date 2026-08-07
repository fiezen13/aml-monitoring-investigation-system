# Statistical harmonization

ABM-BANK generates new agents; it never asserts that records in unrelated public sources describe the same person. Each parameter card states the source, transformation, uncertainty, and sensitivity range.

## Method used in v0.1.0

Population marginals are mapped into coarse banking categories. Generation then applies registered conditional tables in dependency order: customer kind → segment → age/income/region; segment → accounts/opening balance/digital adoption; business segment → turnover/industry; customer segment and transaction type → event intensity/amount/channel. Amounts use registered conditional lognormal models capped by available balance. Recurring salary schedules and segment-specific rates preserve temporal dependence, while stateful balances prevent independent transaction draws.

Public synthetic AML datasets and typology publications inform method and structural motifs only. They do not set Vietnamese demographics, exact amount distributions, or crime prevalence. Scenario counts are benchmark quotas, not estimates.

## Source incompatibility controls

- No row-level joins occur across public sources.
- National population statistics constrain only documented coarse marginals.
- Survey categories are mapped to canonical categories with the mapping recorded as an assumption.
- Public synthetic transaction datasets inform candidate shapes and validation methods, not population identity.
- Low-confidence values remain sensitivity-testable in YAML.

## Validation

Each release records realized customer, account, merchant, transaction, channel, and split distributions in `reports/statistical_summary.json`. These are reproducibility comparisons to their intended parameter targets. Source microdata is not bundled; once an approved local source is supplied, `profile-source` produces quantitative profiles that can replace low-confidence cards without changing generator code.

V0.1.0 uses conditional tables rather than IPF, copulas, or donor matching because no compatible approved microdata combination is present locally. Using a more complex technique without joint evidence would create false precision.
