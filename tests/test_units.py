"""Duration and Frequency: the typed quantities node configs declare."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from rasl.engine.units import Duration, Frequency


class TestDuration:
    @pytest.mark.parametrize(
        ("text", "seconds"),
        [("50ms", 0.05), ("2s", 2.0), ("1.5min", 90.0), ("0ms", 0.0), ("0.25 s", 0.25), ("200MS", 0.2)],
    )
    def test_a_number_with_a_time_unit(self, text: str, seconds: float) -> None:
        assert Duration(text).seconds == pytest.approx(seconds)

    def test_seconds_by_name(self) -> None:
        assert Duration(seconds=2) == Duration("2s")
        assert Duration("50ms").milliseconds == pytest.approx(50.0)

    @pytest.mark.parametrize("value", [30, 30.0, "30", "0"])
    def test_a_bare_number_is_refused(self, value) -> None:
        with pytest.raises(ValueError, match=r"a duration needs a unit, such as \d+ms or \d+s"):
            Duration(value)

    def test_a_frequency_is_refused(self) -> None:
        with pytest.raises(ValueError, match="a duration takes a time, such as 50ms or 2s, not a frequency"):
            Duration("30hz")

    def test_a_negative_time_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot be negative"):
            Duration("-1s")

    @pytest.mark.parametrize("text", ["soon", "5 parsecs", "", "5kg"])
    def test_anything_else_is_refused(self, text: str) -> None:
        with pytest.raises(ValueError):
            Duration(text)

    def test_it_is_a_value(self) -> None:
        assert Duration("1000ms") == Duration("1s")
        assert hash(Duration("1000ms")) == hash(Duration("1s"))
        assert Duration("50ms") < Duration("1s")
        assert Duration("50ms") != Frequency(20)
        assert not Duration("0ms") and Duration("1ms")
        with pytest.raises(AttributeError):
            Duration("1s").seconds = 2  # type: ignore[misc]

    def test_it_prints_as_it_is_written(self) -> None:
        assert str(Duration("50ms")) == "50ms"
        assert str(Duration("1500ms")) == "1.5s"
        assert repr(Duration("0ms")) == "Duration('0s')"


class TestFrequency:
    @pytest.mark.parametrize(
        ("value", "hz"),
        [(30, 30.0), (2.5, 2.5), ("30", 30.0), ("20hz", 20.0), ("30fps", 30.0), ("0.5 Hz", 0.5), ("1khz", 1000.0)],
    )
    def test_a_number_of_hertz(self, value, hz: float) -> None:
        assert Frequency(value).hz == pytest.approx(hz)

    def test_hertz_by_name_and_period(self) -> None:
        assert Frequency(hz=20) == Frequency("20hz")
        assert Frequency(20).period == Duration("50ms")

    def test_a_time_is_refused(self) -> None:
        with pytest.raises(
            ValueError,
            match="a frequency takes a number of hertz, such as 30, 30hz or 30fps, not a time",
        ):
            Frequency("20ms")

    @pytest.mark.parametrize("value", [0, -5, "0hz", "-1"])
    def test_it_must_be_positive(self, value) -> None:
        with pytest.raises(ValueError, match="a frequency must be positive"):
            Frequency(value)

    @pytest.mark.parametrize("value", ["fast", True, None, [30]])
    def test_anything_else_is_refused(self, value) -> None:
        with pytest.raises((ValueError, TypeError)):
            Frequency(value)

    def test_it_prints_in_hertz(self) -> None:
        assert str(Frequency("30fps")) == "30hz"
        assert repr(Frequency(2.5)) == "Frequency('2.5hz')"


class _Settings(BaseModel):
    period: Duration = Duration("50ms")
    fps: Frequency = Frequency(30)


class TestInAConfig:
    """How a node author uses them: as the type of a config field."""

    def test_defaults_are_typed(self) -> None:
        settings = _Settings()
        assert settings.period.seconds == 0.05 and settings.fps.hz == 30.0

    def test_config_text_is_parsed_into_the_type(self) -> None:
        settings = _Settings(period="2s", fps="20hz")
        assert settings.period == Duration("2s") and settings.fps == Frequency(20)
        assert _Settings(fps=25).fps.hz == 25.0
        assert _Settings(period=Duration("1s")).period.seconds == 1.0

    def test_a_wrong_value_is_a_validation_error_that_names_the_field(self) -> None:
        with pytest.raises(ValidationError) as caught:
            _Settings(period=30)
        message = str(caught.value)
        assert "period" in message and "a duration needs a unit, such as 30ms or 30s" in message

    def test_it_writes_back_out_as_text_and_describes_itself_in_the_schema(self) -> None:
        assert _Settings(period="2s").model_dump_json() == '{"period":"2s","fps":"30hz"}'
        properties = _Settings.model_json_schema()["properties"]
        assert properties["period"]["format"] == "rasl-duration"
        assert properties["fps"]["examples"] == [30, "20hz", "30fps"]
