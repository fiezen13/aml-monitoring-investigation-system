"""Parquet release, checksum, and label-free adapter tests."""

import json

from abm.adapters.events import iter_release_events
from abm.exporters.release import ReleaseExporter, load_release, verify_manifest
from abm.validation.release import validate_world


def test_release_round_trip(tmp_path, tiny_world, tiny_config, parameter_registry):
    quality = validate_world(tiny_world, tiny_config, parameter_registry)
    exporter = ReleaseExporter(tiny_config, parameter_registry, tmp_path)
    release = exporter.write(tiny_world, {"quality_report": quality})
    assert verify_manifest(release)["status"] == "PASS"
    loaded = load_release(release)
    assert loaded.table_counts() == tiny_world.table_counts()
    assert validate_world(loaded, tiny_config, parameter_registry)["status"] == "PASS"

    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["logical_world_sha256"] == tiny_world.logical_fingerprint()
    assert manifest["source_ids"]
    assert manifest["scenario_counts"]["STRUCTURING"] >= 1


def test_event_adapter_excludes_ground_truth(tmp_path, tiny_world, tiny_config, parameter_registry):
    release = ReleaseExporter(tiny_config, parameter_registry, tmp_path).write(tiny_world)
    event = next(iter(iter_release_events(release, limit=1)))
    serialized = json.dumps(event).lower()
    assert event["type"] == "bank.transaction.posted.v1"
    assert event["data"]["transaction_id"]
    assert "is_laundering" not in serialized
    assert "scenario_instance_id" not in serialized
    assert "network_id" not in serialized


def test_event_adapter_reads_sharded_large_release(tmp_path, tiny_world, tiny_config, parameter_registry):
    exported = ReleaseExporter(tiny_config, parameter_registry, tmp_path).write(tiny_world)
    large = tmp_path / "ABM-BANK-v9.9.9"
    shard = large / "shards" / "shard-000"
    shard.parent.mkdir(parents=True)
    exported.rename(shard)
    aggregate_fingerprint = "f" * 64
    (large / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": "9.9.9",
                "logical_dataset_sha256": aggregate_fingerprint,
            }
        ),
        encoding="utf-8",
    )

    event = next(iter(iter_release_events(large, limit=1)))

    assert event["source"] == "abm-bank/ABM-BANK-v9.9.9"
    assert event["source_offset"].startswith(aggregate_fingerprint[:24] + "/")
    assert event["data"]["transaction_id"].startswith("TXN-")
