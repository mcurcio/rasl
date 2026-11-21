"""RollingCounter: a count that wraps, carried as an immutable payload."""

from __future__ import annotations

import dataclasses

import pytest

from rasl.signal import FramePayload, MatrixPayload, RollingCounter, get_payload_type


def test_it_is_registered_as_counter_and_is_not_a_matrix() -> None:
    assert get_payload_type("counter") is RollingCounter
    assert RollingCounter.domain == "counter"
    assert not issubclass(RollingCounter, MatrixPayload)


def test_the_defaults() -> None:
    assert RollingCounter() == RollingCounter(0, 1 << 16)


@pytest.mark.parametrize(("value", "modulus"), [(0, 1), (0, 0), (-1, 10), (10, 10), (11, 10)])
def test_a_bad_value_or_modulus_is_refused(value: int, modulus: int) -> None:
    with pytest.raises(ValueError, match="RollingCounter"):
        RollingCounter(value, modulus)


def test_advanced_wraps_and_returns_a_new_counter() -> None:
    counter = RollingCounter(65534)
    assert counter.advanced() == RollingCounter(65535)
    assert counter.advanced(2) == RollingCounter(0)
    assert counter.advanced(-65535) == RollingCounter(65535)
    assert counter == RollingCounter(65534)


def test_advanced_since_counts_across_the_wrap() -> None:
    before = RollingCounter(65530)
    assert before.advanced(10).advanced_since(before) == 10
    assert before.advanced_since(before) == 0
    assert RollingCounter(3, 8).advanced_since(RollingCounter(5, 8)) == 6


def test_advanced_since_refuses_another_modulus() -> None:
    with pytest.raises(ValueError, match="modulus 8 and 16"):
        RollingCounter(1, 8).advanced_since(RollingCounter(1, 16))


def test_it_is_immutable() -> None:
    counter = RollingCounter(1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        counter.value = 2  # type: ignore[misc]
    assert not hasattr(counter, "__dict__")


def test_nothing_coerces_into_a_counter() -> None:
    assert RollingCounter.coerces_from(FramePayload) is False
    assert RollingCounter.coerces_from(MatrixPayload) is False


def test_describe_names_the_value_and_modulus() -> None:
    description = RollingCounter(7, 100).describe()
    assert (description.type_name, description.domain) == ("RollingCounter", "counter")
    assert description.attrs == {"value": 7, "modulus": 100}
