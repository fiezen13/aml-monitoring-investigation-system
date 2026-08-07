"""Evidence registry and reproducibility tests."""

from dataclasses import replace

from abm.generator import AbmBankGenerator


def test_registry_is_complete(parameter_registry):
    assert len(parameter_registry.cards) >= 30
    assert len(parameter_registry.sources) >= 10
    assert all(card["reason"] for card in parameter_registry.cards.values())


def test_same_seed_has_same_fingerprint(tiny_config, parameter_registry, tiny_world):
    repeated = AbmBankGenerator(tiny_config, parameter_registry).generate()
    assert repeated.logical_fingerprint() == tiny_world.logical_fingerprint()


def test_different_seed_changes_fingerprint(tiny_config, parameter_registry, tiny_world):
    changed = replace(tiny_config, simulation_seed=tiny_config.simulation_seed + 1)
    alternate = AbmBankGenerator(changed, parameter_registry).generate()
    assert alternate.logical_fingerprint() != tiny_world.logical_fingerprint()
    assert alternate.table_counts()["customers"] == tiny_world.table_counts()["customers"]


def test_id_namespaces_make_shards_disjoint(tiny_config, parameter_registry):
    first = AbmBankGenerator(replace(tiny_config, id_namespace="S000"), parameter_registry).generate()
    second = AbmBankGenerator(replace(tiny_config, id_namespace="S001"), parameter_registry).generate()

    for table, key in (
        ("customers", "customer_id"),
        ("businesses", "business_id"),
        ("accounts", "account_id"),
        ("devices", "device_id"),
        ("merchants", "merchant_id"),
        ("relationships", "relationship_id"),
        ("sessions", "session_id"),
        ("transactions", "transaction_id"),
    ):
        first_ids = {row[key] for row in getattr(first, table)}
        second_ids = {row[key] for row in getattr(second, table)}
        assert first_ids.isdisjoint(second_ids), table
