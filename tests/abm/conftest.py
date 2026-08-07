"""Shared deterministic ABM smoke fixtures."""

import pytest

from abm.generator import AbmBankGenerator
from abm.registry import ParameterRegistry, SimulationConfig


@pytest.fixture(scope="session")
def tiny_config():
    return SimulationConfig.load("abm/configs/tiny.yaml")


@pytest.fixture(scope="session")
def parameter_registry():
    return ParameterRegistry()


@pytest.fixture(scope="session")
def tiny_world(tiny_config, parameter_registry):
    return AbmBankGenerator(tiny_config, parameter_registry).generate()
