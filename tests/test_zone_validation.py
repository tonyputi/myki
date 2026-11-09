"""Invalid cloud geofencing data must not become a departure from a zone."""

import json

import pytest

from custom_components.myki.utils import AWAY, get_position, get_safe_zones, get_zone

ZONE = {"name": "School", "lat": 10, "lon": 20, "radius": 0.1, "active": 1}
POSITION = {"latitude": 10, "longitude": 20, "accuracy": 25, "type": "WiFi"}


def app_data(zone: dict) -> dict:
    return {
        "current": {"position": dict(POSITION)},
        "settings": {"safe_zone_1": json.dumps(zone)},
    }


@pytest.mark.parametrize("field,value", [
    ("lat", None), ("lat", "invalid"), ("lat", "nan"), ("lat", 91),
    ("lon", "inf"), ("lon", -181), ("radius", None), ("radius", "nan"),
    ("radius", "inf"), ("radius", -1), ("radius", 0),
    ("active", "invalid"), ("active", 2), ("active", 0.5),
])
def test_invalid_zone_is_unknown(field, value):
    data = app_data({**ZONE, field: value})
    assert get_safe_zones(data) is None
    assert get_zone(data) is None


@pytest.mark.parametrize("field", ["lat", "lon", "radius", "active"])
def test_incomplete_zone_is_unknown(field):
    zone = dict(ZONE)
    del zone[field]
    assert get_zone(app_data(zone)) is None


@pytest.mark.parametrize("raw", ["{bad", "[]", "true", "123", {"active": 1}])
def test_malformed_zone_payload_is_unknown(raw):
    data = app_data(ZONE)
    data["settings"]["safe_zone_2"] = raw
    assert get_zone(data) is None


@pytest.mark.parametrize("raw", [None, "", "null"])
def test_unconfigured_zone_slot_is_ignored(raw):
    data = app_data(ZONE)
    data["settings"]["safe_zone_2"] = raw
    assert get_zone(data) == "School"


@pytest.mark.parametrize("settings", [None, [], "invalid"])
def test_invalid_settings_are_unknown(settings):
    data = app_data(ZONE)
    data["settings"] = settings
    assert get_zone(data) is None


@pytest.mark.parametrize("field,value", [
    ("latitude", "nan"), ("latitude", "inf"), ("latitude", 91),
    ("longitude", -181), ("longitude", None),
    ("accuracy", -1), ("accuracy", float("inf")),
])
def test_invalid_position_is_unknown(field, value):
    data = app_data(ZONE)
    data["current"]["position"][field] = value
    assert get_position(data) is None
    assert get_zone(data) is None


@pytest.mark.parametrize("position", [[1], "invalid", True])
def test_malformed_position_is_unknown(position):
    data = app_data(ZONE)
    data["current"]["position"] = position
    assert get_position(data) is None


def test_malformed_current_is_unknown():
    assert get_position({"current": [1]}) is None


def test_disabled_zone_needs_no_geometry():
    data = app_data({"active": "0"})
    assert get_safe_zones(data) == []
    assert get_zone(data) == AWAY


def test_empty_zone_name_uses_slot_key():
    assert get_zone(app_data({**ZONE, "name": "   "})) == "safe_zone_1"


def test_empty_settings_mean_no_configured_zones():
    data = app_data(ZONE)
    data["settings"] = {}
    assert get_zone(data) == AWAY
