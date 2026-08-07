"""Canonical integrity and suitability gates."""

from abm.validation.release import validate_world


def test_all_quality_gates_pass(tiny_world, tiny_config, parameter_registry):
    report = validate_world(tiny_world, tiny_config, parameter_registry)
    assert report["status"] == "PASS"
    assert report["failed"] == 0
    assert report["passed"] == report["check_count"]


def test_no_ground_truth_columns_in_bank_view(tiny_world):
    forbidden = {"scenario_instance_id", "network_id", "is_laundering", "true_controller_id"}
    for table in (
        tiny_world.customers,
        tiny_world.accounts,
        tiny_world.devices,
        tiny_world.relationships,
        tiny_world.transactions,
    ):
        assert forbidden.isdisjoint(table[0])


def test_required_scenario_and_control_families(tiny_world):
    assert {row["scenario_type"] for row in tiny_world.scenario_instances} == {
        "STRUCTURING",
        "RAPID_PASS_THROUGH",
        "MULE_FUNNEL",
        "FAN_IN_FAN_OUT",
        "CIRCULAR_LAYERING",
    }
    assert len({row["scenario_type"] for row in tiny_world.hard_negative_instances}) == 6
