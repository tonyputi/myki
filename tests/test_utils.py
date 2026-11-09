"""Pure payload helpers using synthetic coordinates and reserved phone numbers."""

import json

import pytest

from custom_components.myki.utils import (
    AWAY,
    authorized_phones,
    distance_meters,
    get_battery,
    get_gsm_signal,
    get_model,
    get_position,
    get_steps_today,
    get_zone,
    is_online,
)

HOME_ZONE = {"name": "Home", "lat": 10.0, "lon": 20.0, "radius": 0.2, "active": 1}
SCHOOL_ZONE = {"name": "School", "lat": 10.03, "lon": 20.02, "radius": 0.1, "active": 1}


def payload(lat=10.0, lon=20.0, *, zones=(HOME_ZONE, SCHOOL_ZONE), battery="85", online="1", steps=1200):
    return {
        "current": {
            "position": {"type": "WiFi", "latitude": lat, "longitude": lon, "accuracy": 25},
            "battery": battery, "steps": {"todaySteps": steps},
        },
        "settings": {"online": online, **{
            f"safe_zone_{i}": json.dumps(zone) for i, zone in enumerate(zones, 1)
        }},
        "commands": {"sos_phone_1": "0015555550100", "whitelist_1": "0015555550100,0015555550101"},
    }


def test_distance_meters():
    assert 3900 < distance_meters(10.0, 20.0, 10.03, 20.02) < 4100


@pytest.mark.parametrize("lat,lon,expected", [
    (10.0001, 20.0001, "Home"), (10.0301, 20.0201, "School"), (10.1, 20.1, AWAY),
])
def test_zone(lat, lon, expected):
    assert get_zone(payload(lat, lon)) == expected


def test_zone_inactive_ignored():
    assert get_zone(payload(10.03, 20.02, zones=(HOME_ZONE, {**SCHOOL_ZONE, "active": 0}))) == AWAY


def test_zone_radius_is_kilometers():
    assert get_zone(payload(10.0027, 20.0)) == AWAY
    assert get_zone(payload(10.0009, 20.0)) == "Home"


def test_zone_unnamed_uses_key():
    zone = {key: value for key, value in HOME_ZONE.items() if key != "name"}
    assert get_zone(payload(zones=(zone,))) == "safe_zone_1"


def test_zone_no_position():
    assert get_zone({"current": {}}) is None


def test_position():
    assert get_position(payload()) == (10.0, 20.0, 25, "WiFi")


def test_battery_steps_online():
    data = payload()
    assert get_battery(data) == 85
    assert get_steps_today(data) == 1200
    assert is_online(data) is True
    assert is_online(payload(online="0")) is False
    assert get_battery({"current": {"battery": None}}) is None


def test_authorized_phones():
    data = payload()
    data["commands"].update({"volume_ring": "4", "interval": "120", "whitelist_mode": "1"})
    data["commands"]["sos_phone_2"] = "+15555550102"
    assert authorized_phones(data) == {"0015555550100", "0015555550101", "+15555550102"}


def test_get_model_spot_fw():
    assert get_model({"settings": {"fw": "G36W_test"}}) == "MyKi Spot"


@pytest.mark.parametrize("mode", ["sos", "pet", "asset", ""])
def test_mode_is_not_a_product_model(mode):
    assert get_model({"settings": {"fw": "unknown", "mode": mode}}) == "MyKi tracker"


def test_gsm_signal():
    assert get_gsm_signal({"current": {"gsmSignalStrength": "66"}}) == 66
    assert get_gsm_signal({"current": {}}) is None


@pytest.mark.parametrize("value", [None, "bad", float("inf"), float("nan")])
def test_invalid_numeric_values(value):
    data = {"current": {"battery": value, "gsmSignalStrength": value, "steps": {"todaySteps": value}}}
    assert get_battery(data) is None
    assert get_gsm_signal(data) is None
    assert get_steps_today(data) is None


def test_safe_zone_invalid_values():
    data = payload()
    data["settings"]["safe_zone_3"] = "{bad"
    assert get_zone(data) is None
