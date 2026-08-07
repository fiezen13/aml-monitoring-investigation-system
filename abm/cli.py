"""Command-line interface for profiling, generating, validating, and streaming ABM-BANK."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from abm.adapters.events import iter_release_events, write_jsonl
from abm.exporters.release import load_release, verify_manifest
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

    generate = subparsers.add_parser("generate", help="generate, validate, and write a release")
    generate.add_argument("--config", default="abm/configs/mvp.yaml")
    generate.add_argument("--output-root", default="artifacts")
    generate.add_argument("--overwrite", action="store_true")
    generate.set_defaults(handler=_generate)

    validate = subparsers.add_parser("validate", help="validate a materialized release and its checksums")
    validate.add_argument("--config", default="abm/configs/mvp.yaml")
    validate.add_argument("--release", required=True)
    validate.add_argument("--report")
    validate.set_defaults(handler=_validate_release)

    stream = subparsers.add_parser("stream-sample", help="write label-free transaction event JSONL")
    stream.add_argument("--release", required=True)
    stream.add_argument("--output", required=True)
    stream.add_argument("--limit", type=int, default=1000)
    stream.set_defaults(handler=_stream_sample)
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


def _generate(arguments: argparse.Namespace) -> dict[str, Any]:
    _, result = build_release(arguments.config, arguments.output_root, overwrite=arguments.overwrite)
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


def _stream_sample(arguments: argparse.Namespace) -> dict[str, Any]:
    if arguments.limit < 1:
        raise ValueError("limit must be positive")
    count = write_jsonl(iter_release_events(arguments.release, arguments.limit), arguments.output)
    return {"status": "PASS", "event_count": count, "output": str(Path(arguments.output).resolve())}
