# Data directory

This directory is the repository's local data workspace. Large files are ignored by Git.

- `raw/`: immutable downloaded source datasets, organized by source.
- `profiles/`: machine-readable profiling results derived from approved source data.
- `generated/`: reproducible synthetic datasets, including `ABM-BANK-v<version>/`.
- `aml/`: runtime checkpoints and rejected records used by the legacy AML ingestion pipeline.

The canonical MVP release is generated at:

```text
data/generated/ABM-BANK-v0.1.0/
```

Run `make abm-release` to rebuild it and `make abm-validate` to verify its manifest and Parquet tables. Generated data must not be committed to Git.
