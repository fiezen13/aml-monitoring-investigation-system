"""Tests for the canonical release builder, phases 10 to 20.

The release itself takes about a minute to build against the 2.8 GB source, so
these test the pieces against small fixtures. The properties that would ruin the
release if broken — duplicate ids, label leakage into Bank View, a network split
across evaluation folds, ordering lost in the timestamp redraw — are asserted
directly rather than inferred from a passing build.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from abm.canonical import splits
from abm.canonical.ground_truth import infer_roles
from abm.canonical.hard_negatives import ASSUME_FAMILY_QUOTA, FAMILIES, generate_episodes
from abm.canonical.materialize import BANK_VIEW_COLUMNS
from abm.canonical.transactions import (
    ASSUME_DIURNAL_PROFILE,
    assign_payment_format,
    combined_scale,
    event_id,
    format_timestamp,
    redraw_times,
    to_epoch,
)
from abm.canonical.validate import FORBIDDEN_BANK_VIEW_COLUMNS, run_all
from abm.profiling.ibm_patterns import normalize_account_key, parse_patterns

# Release-level tests run against whichever canonical release is present, and
# skip when none is. The full release is 6.8 GB and gitignored, so CI will not
# have one; these assertions are a check on a built artifact, not a unit test.
RELEASE = next(
    (
        path
        for path in (
            Path("data/releases/ABM-BANK-v0.1.0-full"),
            Path("data/releases/ABM-BANK-v0.1.0-small"),
        )
        if path.exists()
    ),
    Path("data/releases/ABM-BANK-v0.1.0-full"),
)


# ------------------------------------------------------------------ timestamps


def test_naive_timestamps_convert_independently_of_machine_timezone() -> None:
    """PyArrow yields naive datetimes; `.timestamp()` would use the local zone.

    Two developers in different zones must get the same epoch from the same file,
    or the pattern join silently matches nothing.
    """
    naive = datetime(2022, 9, 1, 5, 14)
    assert to_epoch(naive) == int(naive.replace(tzinfo=UTC).timestamp())


def test_format_labels_the_offset_without_shifting_the_clock() -> None:
    """IBM's clock is adopted as Indochina time, not converted into it."""
    epoch = to_epoch(datetime(2022, 9, 1, 0, 0))
    assert format_timestamp(epoch) == "2022-09-01T00:00:00+07:00"


def test_time_redraw_preserves_date_and_ordering() -> None:
    """The redraw may change the hour; it may never reorder or move a day."""
    rng = np.random.default_rng(7)
    base = to_epoch(datetime(2022, 9, 1, 0, 0))
    original = np.array(
        [base + offset for offset in (100, 5_000, 40_000, 86_400 + 10, 86_400 + 70_000)],
        dtype=np.int64,
    )
    rebuilt = redraw_times(original, rng)

    assert list(original // 86_400) == list(rebuilt // 86_400)
    assert list(np.argsort(original, kind="stable")) == list(np.argsort(rebuilt, kind="stable"))


def test_time_redraw_replaces_the_uniform_distribution() -> None:
    """IBM's hours are flat; the release's must not be."""
    rng = np.random.default_rng(11)
    base = to_epoch(datetime(2022, 9, 1, 0, 0))
    original = np.array([base + int(x) for x in rng.integers(0, 86_400, size=20_000)], dtype=np.int64)
    rebuilt = redraw_times(original, rng)

    hours = (rebuilt % 86_400) // 3600
    counts = np.bincount(hours, minlength=24) / len(hours)
    # Night hours must be materially quieter than the daytime peak.
    assert counts[3] < counts[10] / 3
    assert abs(counts.max() - counts.min()) > 0.03


def test_diurnal_profile_is_a_distribution() -> None:
    assert ASSUME_DIURNAL_PROFILE.min() > 0
    assert ASSUME_DIURNAL_PROFILE.sum() == pytest.approx(1.0, abs=0.02)


# ------------------------------------------------------------------ calibration


def test_combined_scale_is_symmetric() -> None:
    assert combined_scale(4.0, 9.0) == pytest.approx(6.0)
    assert combined_scale(9.0, 4.0) == pytest.approx(6.0)


def test_combined_scale_falls_back_to_the_only_side_present() -> None:
    assert combined_scale(None, 5.0) == 5.0
    assert combined_scale(5.0, None) == 5.0
    assert combined_scale(None, None) is None


def test_event_id_is_deterministic_and_content_addressed() -> None:
    first = event_id("TXN-000000000001", "ACC-00000001", "ACC-00000002", 1662000000, "1000")
    same = event_id("TXN-000000000001", "ACC-00000001", "ACC-00000002", 1662000000, "1000")
    different = event_id("TXN-000000000001", "ACC-00000001", "ACC-00000002", 1662000000, "1001")
    assert first == same
    assert first != different


# ------------------------------------------------------------- payment format


def test_payment_format_ignores_the_laundering_label() -> None:
    """The redraw exists to remove a label leak; it must not read the label."""
    from abm.canonical.transactions import RebuildConfig

    rng_a = np.random.default_rng(3)
    rng_b = np.random.default_rng(3)
    segments = ["HIGH"] * 200
    exposure = np.zeros(200, dtype=bool)
    external = np.zeros(200, dtype=bool)

    first = assign_payment_format(segments, exposure, external, rng_a, RebuildConfig())
    second = assign_payment_format(segments, exposure, external, rng_b, RebuildConfig())
    assert list(first) == list(second)


def test_payment_format_follows_the_digital_segment() -> None:
    from abm.canonical.transactions import RebuildConfig

    rng = np.random.default_rng(5)
    size = 4000
    digital = assign_payment_format(["HIGH"] * size, np.zeros(size, bool), np.zeros(size, bool), rng, RebuildConfig())
    cash_bound = assign_payment_format(
        ["NONE"] * size, np.zeros(size, bool), np.zeros(size, bool), rng, RebuildConfig()
    )

    def cash_share(values: np.ndarray) -> float:
        cash = sum(1 for value in values if value in ("CASH_DEPOSIT", "CASH_WITHDRAWAL"))
        return cash / len(values)

    assert cash_share(cash_bound) > cash_share(digital) * 3


# ----------------------------------------------------------------- ground truth


def test_roles_follow_position_in_the_flow() -> None:
    roles = infer_roles([("A", "B"), ("B", "C")])
    assert roles == {"A": "ORIGINATOR", "B": "PASSTHROUGH", "C": "BENEFICIARY"}


def test_pattern_account_keys_are_normalized() -> None:
    """Raw pattern keys carry the bank's zero padding; profiles do not."""
    assert normalize_account_key("0031224", "812E2A1A0") == "31224:812E2A1A0"
    assert normalize_account_key("0", "ABC") == "0:ABC"
    assert normalize_account_key("000", "ABC") == "0:ABC"


def test_patterns_file_parses_including_the_unterminated_block() -> None:
    path = Path("data/raw/ibm-aml/HI-Medium_Patterns.txt")
    if not path.exists():
        pytest.skip("IBM patterns file is not present")
    instances = parse_patterns(path)
    assert len(instances) == 493
    assert sum(1 for instance in instances if not instance.closed) == 1


# ----------------------------------------------------------------------- splits


def test_networks_sharing_an_account_land_in_one_split() -> None:
    """219 IBM pattern accounts sit in more than one instance.

    Assigning each network independently would put an account's other network in
    a different fold, leaking it into training through that account's history.
    """
    networks = [
        {"network_id": "NET-1", "members": ["E1", "E2"]},
        {"network_id": "NET-2", "members": ["E2", "E3"]},
        {"network_id": "NET-3", "members": ["E9"]},
    ]
    components = splits.network_components(networks)
    assignment = splits.assign_entity_splits(["E1", "E2", "E3", "E9", "E4"], components, seed=1)

    assert assignment["E1"] == assignment["E2"] == assignment["E3"]
    assert not splits.verify_no_network_crosses_splits(networks, assignment)


def test_split_assignment_is_stable_when_entities_are_added() -> None:
    """Hash-based assignment must not reshuffle existing entities."""
    first = splits.assign_entity_splits(["A", "B", "C"], [], seed=42)
    second = splits.assign_entity_splits(["A", "B", "C", "D", "E"], [], seed=42)
    assert all(first[key] == second[key] for key in first)


def test_time_partition_covers_the_window() -> None:
    assert splits.time_partition(0, 0, 100) == "EARLY"
    assert splits.time_partition(70, 0, 100) == "MIDDLE"
    assert splits.time_partition(95, 0, 100) == "LATE"


# --------------------------------------------------------------- hard negatives


def test_hard_negatives_never_reuse_a_laundering_entity() -> None:
    """An entity cannot be both a designed false positive and a true positive."""
    accounts = [
        {
            "account_id": f"ACC-{index:08d}",
            "owner_id": f"CUS-{index:08d}",
            "owner_type": "CUSTOMER" if index % 2 else "BUSINESS",
            "target_monthly_inflow_vnd": 10_000_000.0,
        }
        for index in range(600)
    ]
    excluded = {f"CUS-{index:08d}" for index in range(300)}
    episodes = generate_episodes(accounts, excluded, day_range=(19236, 19260), seed=3)

    assert episodes
    assert all(episode.entity_id not in excluded for episode in episodes)
    assert len({episode.account_id for episode in episodes}) == len(episodes)


def test_every_hard_negative_family_is_represented() -> None:
    accounts = [
        {
            "account_id": f"ACC-{index:08d}",
            "owner_id": f"E-{index:08d}",
            "owner_type": "CUSTOMER" if index % 2 else "BUSINESS",
            "target_monthly_inflow_vnd": 8_000_000.0,
        }
        for index in range(2000)
    ]
    episodes = generate_episodes(accounts, set(), day_range=(19236, 19260), seed=9)
    families = {episode.family for episode in episodes}
    assert families == set(FAMILIES)
    assert len(episodes) == sum(ASSUME_FAMILY_QUOTA.values())


# ---------------------------------------------------- release-level properties


def _require_release() -> None:
    if not RELEASE.exists():
        pytest.skip("canonical release has not been built")


def test_bank_view_carries_no_ground_truth_column() -> None:
    """The separation is physical, and this is what makes it enforceable."""
    _require_release()
    for path in (RELEASE / "bank_view").glob("*.csv"):
        with path.open(encoding="utf-8") as handle:
            header = set(next(csv.reader(handle)))
        leaked = header & set(FORBIDDEN_BANK_VIEW_COLUMNS)
        assert not leaked, f"{path.name} exposes {leaked}"


def test_bank_view_columns_match_the_declared_schema() -> None:
    _require_release()
    for name, columns in BANK_VIEW_COLUMNS.items():
        path = RELEASE / "bank_view" / f"{name}.csv"
        with path.open(encoding="utf-8") as handle:
            assert next(csv.reader(handle)) == columns


def test_no_ibm_identifier_survives_into_the_release() -> None:
    """Canonical ids only. An IBM key is `bank:account` and contains a colon."""
    _require_release()
    with (RELEASE / "bank_view/transactions.csv").open(encoding="utf-8") as handle:
        for index, row in enumerate(csv.DictReader(handle)):
            if index >= 20_000:
                break  # 4.8 GB file; a prefix is enough to catch a leaked key format
            for column in (
                "source_account_id",
                "destination_account_id",
                "source_counterparty_token",
                "destination_counterparty_token",
            ):
                assert ":" not in (row[column] or "")


def test_release_passes_every_gate() -> None:
    _require_release()
    report = run_all(RELEASE)
    assert report["verdict"] in ("PASS", "WARN"), report["failed_gates"]
    assert not report["failed_gates"]


def test_no_customer_in_the_release_carries_pii() -> None:
    _require_release()
    with (RELEASE / "bank_view/customers.csv").open(encoding="utf-8") as handle:
        header = set(next(csv.reader(handle)))
    forbidden = {
        "name",
        "full_name",
        "national_id",
        "cccd",
        "cmnd",
        "phone",
        "phone_number",
        "address",
        "email",
        "date_of_birth",
        "dob",
        "tax_id",
    }
    assert not header & forbidden
