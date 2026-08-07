"""Phase 19 — provenance. Every release must be auditable back to its sources.

The manifest answers, for any row in the release: which bytes did this come from,
which code produced it, and what was assumed on the way. Two chains have to be
traceable end to end.

```text
IBM AML CSV (sha256) -> source profile -> behavior profile -> archetype
                     -> matched account -> calibrated scale -> transaction

World Bank indicator (cached, checksummed) -> derived distribution
                     -> KYC generator -> customer attributes
```

`known_limitations` is required and must not be empty. A release that claims no
limitations is a release nobody checked.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MANIFEST_SCHEMA_VERSION = "1.0"


def git_commit() -> str | None:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False)
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def file_checksums(release: Path) -> dict[str, dict[str, Any]]:
    """SHA-256, byte size, and row count for every file in the release."""
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(release.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        digest = hashlib.sha256()
        rows = 0
        with path.open("rb") as handle:
            while chunk := handle.read(1 << 20):
                digest.update(chunk)
                rows += chunk.count(b"\n")
        relative = str(path.relative_to(release))
        entries[relative] = {
            "sha256": digest.hexdigest(),
            "size_bytes": path.stat().st_size,
            "data_rows": max(rows - 1, 0) if path.suffix == ".csv" else None,
        }
    return entries


def build_manifest(
    release: Path,
    *,
    dataset_id: str,
    version: str,
    seed: int,
    counts: dict[str, int],
    window: dict[str, Any],
    selection_stats: dict[str, Any],
    ibm_source: dict[str, Any],
    public_sources: list[str],
    source_registry_version: str,
    distributions_version: str,
    assumptions: list[dict[str, Any]],
    validation: dict[str, Any],
    known_limitations: list[str],
) -> dict[str, Any]:
    if not known_limitations:
        raise ValueError("known_limitations must not be empty")

    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": dataset_id,
        "dataset_version": version,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generator_git_commit": git_commit(),
        "seed": seed,
        "schema_version": "1.0",
        "release_owner": "Bao",
        "ibm_source": ibm_source,
        "public_sources": public_sources,
        "source_registry_version": source_registry_version,
        "distributions_version": distributions_version,
        "observation_window": window,
        "subgraph_selection": selection_stats,
        "counts": counts,
        "assumptions": assumptions,
        "validation": {
            "verdict": validation["verdict"],
            "failed_gates": validation["failed_gates"],
            "warned_gates": validation["warned_gates"],
            "gate_verdicts": {name: gate["verdict"] for name, gate in validation["gates"].items()},
        },
        "prevalence_claim": False,
        "prevalence_note": (
            "Scenario counts are benchmark coverage decisions. The flagged-entity "
            "rate in this release is an artifact of subgraph selection, which seeds "
            "on laundering patterns, and is far above any real base rate."
        ),
        "known_limitations": known_limitations,
        "files": file_checksums(release),
    }


def write_manifest(manifest: dict[str, Any], release: Path) -> Path:
    path = release / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
