"""Checks that hold for every test."""

from __future__ import annotations

import gc
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _garbage_collection_is_left_on() -> Iterator[None]:
    """A scheduler turns automatic collection off and freezes the heap; a test that starts one
    and does not stop it would leave every later test running that way."""
    yield
    assert gc.isenabled(), "the test left automatic garbage collection off (Scheduler.stop())"
    assert gc.get_freeze_count() == 0, "the test left the heap frozen (Scheduler.stop())"
