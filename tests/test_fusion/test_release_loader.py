from __future__ import annotations

import pytest

from scripts.load_fusion_release import _psycopg_url, stable_id


def test_stable_release_ids_are_deterministic_and_namespaced() -> None:
    first = stable_id("BAT-FUS-", "source-sha", "7d", "model-v2", length=16)
    second = stable_id("BAT-FUS-", "source-sha", "7d", "model-v2", length=16)
    changed = stable_id("BAT-FUS-", "source-sha", "7d", "model-v3", length=16)

    assert first == second
    assert first.startswith("BAT-FUS-")
    assert len(first) == len("BAT-FUS-") + 16
    assert changed != first


def test_sqlalchemy_psycopg_url_is_converted_for_driver() -> None:
    result = _psycopg_url("postgresql+psycopg://fin07:secret@localhost:5432/fin07")

    assert result == "postgresql://fin07:secret@localhost:5432/fin07"


def test_non_postgres_loader_url_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        _psycopg_url("sqlite:///local.db")
