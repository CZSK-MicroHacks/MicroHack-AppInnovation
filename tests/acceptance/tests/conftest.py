"""Shared paths for acceptance contract tests."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the root of the checked-out repository."""
    return Path(__file__).resolve().parents[3]
