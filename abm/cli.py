"""Command-line interface for profiling, generating, validating, and streaming ABM-BANK."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from abm.adapters.events import iter_release_events, write_jsonl
from abm.adapters.kafka import publish_release
from abm.exporters.release import load_release, verify_manifest
from abm.large_release import build_large_release, validate_large_release
from abm.profiling.ibm_behavior import build_account_behavior_profiles
from abm.profiling.ibm_source import profile_ibm_source
from abm.profiling.ibm_source import write_profile as write_ibm_profile
from abm.profiling.profile_source import profile_source, write_profile
from abm.registry import ParameterRegistry, SimulationConfig
from abm.release import build_release
from abm.validation.release import validate_world


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="abm-bank", description="ABM-BANK synthetic dataset toolkit")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parameters = subparsers.add_parser("validate-parameters", help="validate evidence-linked parameter cards")
    parameters.set_defaults(handler=_validate_parameters)

    profile = subparsers.add_parser("profile-source", help="profile a CSV, TSV, or Parquet source")
    profile.add_argument("source")
    profile.add_argument("--source-id", required=True)
    profile.add_argument("--output", required=True)
    profile.add_argument("--source-column")
    profile.add_argument("--target-column")
    profile.add_argument("--time-column")
    profile.set_defaults(handler=_profile_source)

    profile_ibm = subparsers.add_parser("profile-ibm", help="profile the raw IBM AML transaction CSV (rebuild phase 1)")
    profile_ibm.add_argument("--input", required=True)
    profile_ibm.add_argument("--output", default="artifacts/source_profiles/ibm_aml_profile.json")
    profile_ibm.add_argument(
        "--max-rows", type=int, help="rehearse on a prefix; the profile records that it is truncated"
    )
    profile_ibm.set_defaults(handler=_profile_ibm)

    profile_behavior = subparsers.add_parser(
        "profile-ibm-behavior",
        help="derive per-account behavior profiles from the IBM CSV (rebuild phase 2)",
    )
    profile_behavior.add_argument("--input", required=True)
    profile_behavior.add_argument("--output", default="artifacts/intermediate/ibm_account_behavior_profiles.csv")
    profile_behavior.add_argument("--report", default="artifacts/source_profiles/ibm_account_behavior_summary.json")
    profile_behavior.add_argument("--accounts", help="optional HI-*_accounts.csv for entity context")
    profile_behavior.add_argument("--max-rows", type=int)
    profile_behavior.set_defaults(handler=_profile_ibm_behavior)

    archetypes = subparsers.add_parser(
        "derive-archetypes", help="cluster IBM account behavior into archetypes (rebuild phase 3)"
    )
    archetypes.add_argument("--input", default="artifacts/intermediate/ibm_account_behavior_profiles.csv")
    archetypes.add_argument("--output", default="artifacts/intermediate/ibm_account_archetypes.csv")
    archetypes.add_argument("--report", default="artifacts/source_profiles/ibm_archetypes.json")
    archetypes.add_argument("--min-transactions", type=int, default=10)
    archetypes.add_argument("--clusters", type=int, help="fix k instead of selecting it by silhouette")
    archetypes.add_argument("--seed", type=int, default=20260807)
    archetypes.set_defaults(handler=_derive_archetypes)

    profile_sources = subparsers.add_parser(
        "profile-sources", help="acquire and profile Vietnam public sources (rebuild phases 4-5)"
    )
    profile_sources.add_argument("--cache-dir", default="data/raw/worldbank")
    profile_sources.add_argument("--output", default="data/source_registry/distributions/vn_population.yaml")
    profile_sources.add_argument("--refresh", action="store_true", help="re-fetch instead of using the cache")
    profile_sources.set_defaults(handler=_profile_sources)

    generate_kyc = subparsers.add_parser(
        "generate-kyc", help="generate KYC, match to IBM behavior, and calibrate (rebuild phases 6-9)"
    )
    generate_kyc.add_argument("--output-dir", default="artifacts/intermediate/kyc_preview")
    generate_kyc.add_argument("--individuals", type=int, default=5000)
    generate_kyc.add_argument("--businesses", type=int, default=800)
    generate_kyc.add_argument("--seed", type=int, default=20260807)
    generate_kyc.add_argument("--cache-dir", default="data/raw/worldbank")
    generate_kyc.set_defaults(handler=_generate_kyc)

    canonical = subparsers.add_parser("build-release", help="build the canonical CSV release (rebuild phases 10-20)")
    canonical.add_argument("--version", default="0.1.0-small")
    canonical.add_argument("--output-root", default="data/releases")
    canonical.add_argument("--accounts", type=int, default=6000)
    canonical.add_argument("--patterns", type=int, default=150)
    canonical.add_argument("--seed", type=int, default=20260807)
    canonical.add_argument(
        "--mode",
        choices=["subgraph", "full"],
        default="subgraph",
        help="'full' keeps every IBM account and pattern; 'subgraph' carves a connected slice",
    )
    canonical.set_defaults(handler=_build_canonical_release)

    compare_ibm = subparsers.add_parser("compare-ibm", help="compare a release against the raw IBM source it came from")
    compare_ibm.add_argument("--release", required=True)
    compare_ibm.add_argument("--output", help="write the full report to this path")
    compare_ibm.set_defaults(handler=_compare_ibm)

    validate_canonical = subparsers.add_parser(
        "validate-release", help="run every quality gate against a materialized CSV release"
    )
    validate_canonical.add_argument("--release", required=True)
    validate_canonical.set_defaults(handler=_validate_canonical_release)

    generate = subparsers.add_parser("generate", help="generate, validate, and write a release")
    generate.add_argument("--config", default="abm/configs/mvp.yaml")
    generate.add_argument("--output-root", default="data/generated")
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=_generate)

    large = subparsers.add_parser("generate-large", help="generate a bounded-memory multi-GB release")
    large.add_argument("--config", default="abm/configs/large.yaml")
    large.add_argument("--output-root", default="data/generated")
    large.add_argument("--overwrite", action="store_true")
    large.set_defaults(handler=_generate_large)

    validate = subparsers.add_parser("validate", help="validate a materialized release and its checksums")
    validate.add_argument("--config", default="abm/configs/mvp.yaml")
    validate.add_argument("--release", required=True)
    validate.add_argument("--report")
    validate.set_defaults(handler=_validate_release)

    validate_large = subparsers.add_parser("validate-large", help="validate every shard in a large release")
    validate_large.add_argument("--config", default="abm/configs/large.yaml")
    validate_large.add_argument("--release", required=True)
    validate_large.add_argument("--workers", type=int, default=6)
    validate_large.set_defaults(handler=_validate_large)

    stream = subparsers.add_parser("stream-sample", help="write label-free transaction event JSONL")
    stream.add_argument("--release", required=True)
    stream.add_argument("--output", required=True)
    stream.add_argument("--limit", type=int, default=1000)
    stream.set_defaults(handler=_stream_sample)

    publish = subparsers.add_parser("publish", help="publish canonical ABM events to Kafka")
    publish.add_argument("--release", required=True)
    publish.add_argument("--bootstrap-servers", default="localhost:29092")
    publish.add_argument("--topic", default="bank.transactions.raw.v1")
    publish.add_argument("--limit", type=int, default=1000)
    publish.set_defaults(handler=_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    result = arguments.handler(arguments)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _validate_parameters(_: argparse.Namespace) -> dict[str, Any]:
    registry = ParameterRegistry()
    return {
        "status": "PASS",
        "registry_version": registry.version,
        "parameter_count": len(registry.cards),
        "source_count": len(registry.sources),
        "registry_sha256": registry.fingerprint(),
    }


def _profile_source(arguments: argparse.Namespace) -> dict[str, Any]:
    report = profile_source(
        arguments.source,
        source_id=arguments.source_id,
        source_column=arguments.source_column,
        target_column=arguments.target_column,
        time_column=arguments.time_column,
    )
    path = write_profile(report, arguments.output)
    return {"status": "PASS", "profile": str(path.resolve()), "row_count": report["row_count"]}


def _report_progress(label: str) -> Any:
    """Print a row counter to stderr so a multi-minute pass is not a blank screen."""
    state = {"next": 5_000_000}

    def report(rows: int) -> None:
        if rows >= state["next"]:
            print(f"  {label}: {rows:,} rows", file=sys.stderr, flush=True)
            state["next"] += 5_000_000

    return report


def _profile_ibm(arguments: argparse.Namespace) -> dict[str, Any]:
    source = Path(arguments.input)
    report = profile_ibm_source(source, max_rows=arguments.max_rows, progress=_report_progress("profile-ibm"))
    path = write_ibm_profile(report, Path(arguments.output))
    return {
        "status": "PASS",
        "profile": str(path.resolve()),
        "row_count": report["row_count"],
        "sha256": report["source"]["sha256"],
        "truncated_run": report["truncated_run"],
    }


def _profile_ibm_behavior(arguments: argparse.Namespace) -> dict[str, Any]:
    return build_account_behavior_profiles(
        Path(arguments.input),
        output=Path(arguments.output),
        report=Path(arguments.report),
        accounts=Path(arguments.accounts) if arguments.accounts else None,
        max_rows=arguments.max_rows,
        progress=_report_progress("profile-ibm-behavior"),
    )


def _derive_archetypes(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.archetypes.derive import derive_archetypes

    return derive_archetypes(
        Path(arguments.input),
        output=Path(arguments.output),
        report=Path(arguments.report),
        min_transactions=arguments.min_transactions,
        k=arguments.clusters,
        seed=arguments.seed,
    )


def _profile_sources(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.sources.vn_distributions import build_all, write_distributions
    from abm.sources.worldbank import acquire

    acquisition = acquire(Path(arguments.cache_dir), refresh=arguments.refresh)
    profile = Path("artifacts/source_profiles/vn_worldbank_acquisition.json")
    profile.parent.mkdir(parents=True, exist_ok=True)
    profile.write_text(json.dumps(acquisition, indent=2, sort_keys=True), encoding="utf-8")

    distributions = build_all(acquisition["values"])
    path = write_distributions(distributions, Path(arguments.output))
    return {
        "status": "PASS",
        "indicators_acquired": acquisition["indicators_acquired"],
        "indicators_unavailable": acquisition["indicators_unavailable"],
        "acquisition_profile": str(profile.resolve()),
        "distributions": str(path.resolve()),
        "unresolved": distributions["unresolved"],
    }


def _generate_kyc(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.kyc.pipeline import load_candidate_accounts, run
    from abm.sources.vn_distributions import build_all
    from abm.sources.worldbank import acquire

    acquisition = acquire(Path(arguments.cache_dir))
    distributions = build_all(acquisition["values"])
    archetypes = json.loads(Path("artifacts/source_profiles/ibm_archetypes.json").read_text(encoding="utf-8"))[
        "archetypes"
    ]
    pools = load_candidate_accounts(
        Path("artifacts/intermediate/ibm_account_archetypes.csv"),
        Path("artifacts/intermediate/ibm_account_behavior_profiles.csv"),
    )
    summary = run(
        distributions,
        acquisition["values"],
        archetypes=archetypes,
        candidate_accounts=pools,
        output_dir=Path(arguments.output_dir),
        individuals=arguments.individuals,
        business_count=arguments.businesses,
        seed=arguments.seed,
    )
    return {"status": "PASS", **summary["counts"], "output_dir": arguments.output_dir}


def _build_canonical_release(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.canonical.build import ReleaseConfig
    from abm.canonical.release import build_and_validate

    return build_and_validate(
        config=ReleaseConfig(
            output_root=Path(arguments.output_root),
            version=arguments.version,
            target_accounts=arguments.accounts,
            target_patterns=arguments.patterns,
            seed=arguments.seed,
            mode=arguments.mode,
        )
    )


def _compare_ibm(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.canonical.ibm_comparison import compare

    report = compare(
        Path(arguments.release),
        ibm_profile_path=Path("artifacts/source_profiles/ibm_aml_profile.json"),
        ibm_behavior_csv=Path("artifacts/intermediate/ibm_account_behavior_profiles.csv"),
    )
    destination = Path(arguments.output or Path(arguments.release) / "reports" / "ibm_comparison.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "verdict": report["verdict"],
        "coverage": report["coverage"],
        "features_outside_tolerance": report["features_outside_tolerance"],
        "report": str(destination),
    }


def _validate_canonical_release(arguments: argparse.Namespace) -> dict[str, Any]:
    from abm.canonical.validate import run_all

    report = run_all(Path(arguments.release))
    return {
        "verdict": report["verdict"],
        "failed_gates": report["failed_gates"],
        "warned_gates": report["warned_gates"],
        "gate_verdicts": {name: gate["verdict"] for name, gate in report["gates"].items()},
    }


def _generate(arguments: argparse.Namespace) -> dict[str, Any]:
    _, result = build_release(arguments.config, arguments.output_root, overwrite=arguments.overwrite)
    return result


def _generate_large(arguments: argparse.Namespace) -> dict[str, Any]:
    _, result = build_large_release(arguments.config, arguments.output_root, overwrite=arguments.overwrite)
    return result


def _validate_release(arguments: argparse.Namespace) -> dict[str, Any]:
    config = SimulationConfig.load(arguments.config)
    registry = ParameterRegistry()
    manifest = verify_manifest(arguments.release)
    world = load_release(arguments.release)
    report = validate_world(world, config, registry)
    result = {"status": "PASS", "manifest": manifest, "quality": report}
    if arguments.report:
        path = Path(arguments.report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result["report"] = str(path.resolve())
    return result


def _validate_large(arguments: argparse.Namespace) -> dict[str, Any]:
    return validate_large_release(
        arguments.release,
        arguments.config,
        workers=arguments.workers,
    )


def _stream_sample(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.limit < 1:
        raise ValueError("limit must be positive")
    count = write_jsonl(iter_release_events(arguments.release, arguments.limit), arguments.output)
    return {"status": "PASS", "event_count": count, "output": str(Path(arguments.output).resolve())}


def _publish(arguments: argparse.Namespace) -> dict[str, Any]:
    return publish_release(
        arguments.release,
        bootstrap_servers=arguments.bootstrap_servers,
        topic=arguments.topic,
        limit=arguments.limit,
    )


# `python -m abm` is the documented entry point, but `python -m abm.cli` reads
# naturally enough that people type it. Both should work rather than one exiting
# silently with status 0.
if __name__ == "__main__":
    raise SystemExit(main())
