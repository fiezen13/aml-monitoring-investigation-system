# Parameter methodology

All material simulation choices live in `abm/parameters/*.yaml`. Python code requests values by stable `parameter_id`; missing and duplicate IDs fail before generation.

Every card contains a description, value, source IDs, derivation method, assumption flag, confidence, sensitivity range, simulation effect, and rationale. Source IDs must resolve in `abm/sources/source_registry.yaml`. Evidence-free parameters require an explicit governance or assumption reason. The validator rejects invalid confidence values, missing fields, unregistered sources, and unexplained assumptions.

Confidence means:

- `high`: direct contract/governance rule or strong representative evidence;
- `medium`: credible evidence requiring a coarse mapping;
- `low`: explicit benchmark assumption or weak population transferability.

The registry intentionally separates two concepts: population calibration and benchmark construction. AML and hard-negative quotas define coverage for model evaluation and make no prevalence claim. The release manifest hashes the canonical registry, so parameter changes create a detectable release change.

Review workflow: profile an approved source; register its Source Card; record the derivation; revise a card and sensitivity bounds; increment the registry/release version; run the tiny deterministic tests; generate the MVP; review realized statistical reports; approve the manifest.
