"""Tests for delivery profiles and their persisted defaults.

All of these run offline: the module only touches JSON under DOUBLECHIN_HOME.
"""

from __future__ import annotations

import json

import pytest

from double_chin import delivery


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DOUBLECHIN_HOME", str(tmp_path))
    return tmp_path


def test_neutral_profile_matches_engine_defaults():
    from double_chin.engine import (
        DEFAULT_CFG_WEIGHT,
        DEFAULT_EXAGGERATION,
        DEFAULT_RATE,
        DEFAULT_TEMPERATURE,
    )

    assert delivery.NEUTRAL_PROFILE.exaggeration == DEFAULT_EXAGGERATION
    assert delivery.NEUTRAL_PROFILE.cfg_weight == DEFAULT_CFG_WEIGHT
    assert delivery.NEUTRAL_PROFILE.temperature == DEFAULT_TEMPERATURE
    assert delivery.NEUTRAL_PROFILE.rate == DEFAULT_RATE


def test_tuned_profile_is_expressible_on_the_sliders():
    # The studio sliders move in 0.05 steps; a tuned value the user cannot
    # dial back in by hand would make the preset button unreproducible.
    for value in delivery.TUNED_PROFILE.as_dict().values():
        steps = value / 0.05
        assert abs(steps - round(steps)) < 1e-6


def test_from_mapping_round_trip():
    data = {"exaggeration": 0.4, "cfg_weight": 0.65, "temperature": 0.75, "rate": 1.05}
    profile = delivery.DeliveryProfile.from_mapping(data)
    assert profile.as_dict() == data


@pytest.mark.parametrize(
    "field,value",
    [
        ("exaggeration", -0.1),
        ("exaggeration", 1.5),
        ("cfg_weight", 2.0),
        ("temperature", 0.0),
        ("temperature", 2.5),
        ("rate", 0.1),
        ("rate", 3.0),
    ],
)
def test_from_mapping_rejects_out_of_range(field, value):
    data = delivery.NEUTRAL_PROFILE.as_dict() | {field: value}
    with pytest.raises(ValueError, match=field):
        delivery.DeliveryProfile.from_mapping(data)


def test_from_mapping_rejects_missing_and_non_numeric():
    partial = {"exaggeration": 0.5}
    with pytest.raises(ValueError):
        delivery.DeliveryProfile.from_mapping(partial)

    bad = delivery.NEUTRAL_PROFILE.as_dict() | {"rate": "fast"}
    with pytest.raises(ValueError):
        delivery.DeliveryProfile.from_mapping(bad)


def test_from_mapping_ignores_unknown_keys():
    data = delivery.NEUTRAL_PROFILE.as_dict() | {"seed": 7, "voice": "owner"}
    assert delivery.DeliveryProfile.from_mapping(data) == delivery.NEUTRAL_PROFILE


def test_load_defaults_without_a_file_returns_tuned(home):
    assert not delivery.defaults_path().exists()
    assert delivery.load_defaults() == delivery.TUNED_PROFILE


def test_save_then_load_round_trip(home):
    profile = delivery.DeliveryProfile(0.35, 0.7, 0.6, 0.95)
    delivery.save_defaults(profile)

    assert delivery.load_defaults() == profile
    stored = json.loads(delivery.defaults_path().read_text())
    assert stored["exaggeration"] == 0.35


def test_load_defaults_falls_back_on_corrupt_json(home, caplog):
    delivery.defaults_path().parent.mkdir(parents=True, exist_ok=True)
    delivery.defaults_path().write_text("{not json at all")

    assert delivery.load_defaults() == delivery.TUNED_PROFILE
    assert "delivery.json" in caplog.text


def test_load_defaults_falls_back_on_out_of_range_file(home, caplog):
    delivery.save_defaults(delivery.NEUTRAL_PROFILE)
    data = json.loads(delivery.defaults_path().read_text())
    data["temperature"] = 9.9
    delivery.defaults_path().write_text(json.dumps(data))

    assert delivery.load_defaults() == delivery.TUNED_PROFILE
    assert "temperature" in caplog.text


def test_clear_defaults_is_idempotent(home):
    delivery.save_defaults(delivery.DeliveryProfile(0.4, 0.4, 0.7, 1.0))
    delivery.clear_defaults()
    delivery.clear_defaults()

    assert not delivery.defaults_path().exists()
    assert delivery.load_defaults() == delivery.TUNED_PROFILE


def test_save_defaults_rejects_an_invalid_profile(home):
    with pytest.raises(ValueError):
        delivery.save_defaults(delivery.DeliveryProfile(0.5, 0.5, 5.0, 1.0))
    assert not delivery.defaults_path().exists()


def test_save_defaults_does_not_clobber_on_write_failure(home, monkeypatch):
    good = delivery.DeliveryProfile(0.4, 0.6, 0.7, 1.0)
    delivery.save_defaults(good)

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(delivery.os, "replace", boom)
    with pytest.raises(OSError):
        delivery.save_defaults(delivery.DeliveryProfile(0.9, 0.9, 1.5, 1.5))

    assert delivery.load_defaults() == good
