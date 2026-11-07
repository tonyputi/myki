"""Tests for pure payload helpers (no Home Assistant dependencies)."""

import importlib.util
import json
from pathlib import Path
import sys

_UTILS = Path(__file__).parent.parent / "custom_components" / "myki" / "utils.py"
_spec = importlib.util.spec_from_file_location("myki_utils", _UTILS)
assert _spec and _spec.loader
utils = importlib.util.module_from_spec(_spec)
sys.modules["myki_utils"] = utils
_spec.loader.exec_module(utils)

from myki_utils import (  # noqa: E402
    AWAY,
    authorized_phones,
    distance_meters,
    get_battery,
    get_gsm_signal as utils_get_gsm_signal,
    get_model as utils_get_model,
    get_position,
    get_steps_today,
    get_zone,
    is_online,
)

HOME_ZONE = {"name": "Home", "lat": 35.92414252073232, "lon": 14.453322999179365,
             "radius": 0.2122035115328407, "active": 1, "profile": 1}
SCHOOL_ZONE = {"name": "School", "lat": 35.90756514655395, "lon": 14.491658471524715,
               "radius": 0.12734466791152954, "active": 1, "profile": 1}


def payload(lat, lon, *, zones=(HOME_ZONE, SCHOOL_ZONE), battery="85", online="1",
            steps=1200, extra_settings=None):
    settings = {
        f"safe_zone_{i}": json.dumps(z) for i, z in enumerate(zones, start=1)
    }
    if extra_settings:
        settings.update(extra_settings)
    return {
        "current": {
            "takenat": "2025-11-07 12:37:29",
            "position": {"type": "WiFi", "latitude": lat, "longitude": lon, "accuracy": 25},
            "battery": battery,
            "steps": {"allSteps": 1353915, "todaySteps": steps},
        },
        "settings": {"online": online, "nickname": "Kid", **settings},
        "commands": {"sos_phone_1": "0035679248232", "whitelist_1": "0035679248232,0035699859524"},
    }


def test_distance_meters():
    # ~ 3.4 km between home and school in the sample data
    d = distance_meters(35.92414252073232, 14.453322999179365, 35.90756514655395, 14.491658471524715)
    assert 3850 < d < 3950


def test_zone_home():
    # at the home zone center
    assert get_zone(payload(35.924170744577, 14.455025326271)) == "Home"


def test_zone_school():
    assert get_zone(payload(35.9076, 14.4917)) == "School"


def test_zone_away():
    # far from both zones
    assert get_zone(payload(35.85, 14.40)) == AWAY


def test_zone_inactive_ignored():
    inactive = dict(SCHOOL_ZONE, active=0)
    assert get_zone(payload(35.9076, 14.4917, zones=(HOME_ZONE, inactive))) == AWAY


def test_zone_radius_is_kilometers():
    # 300 m from home center: radius is 0.212 km = 212 m -> outside
    assert get_zone(payload(35.92414252073232 + 0.0027, 14.453322999179365)) == AWAY
    # 100 m -> inside
    assert get_zone(payload(35.92414252073232 + 0.0009, 14.453322999179365)) == "Home"


def test_zone_unnamed_uses_key():
    unnamed = {k: v for k, v in HOME_ZONE.items() if k != "name"}
    assert get_zone(payload(35.924170744577, 14.455025326271, zones=(unnamed,))) == "safe_zone_1"


def test_zone_no_position():
    assert get_zone({"current": {}}) is None


def test_position():
    lat, lon, acc, typ = get_position(payload(35.9, 14.4))
    assert (lat, lon, acc, typ) == (35.9, 14.4, 25, "WiFi")


def test_battery_steps_online():
    p = payload(35.9, 14.4)
    assert get_battery(p) == 85
    assert get_steps_today(p) == 1200
    assert is_online(p) is True
    assert is_online(payload(35.9, 14.4, online="0")) is False
    assert get_battery({"current": {"battery": None}}) is None


def test_authorized_phones():
    phones = authorized_phones(payload(35.9, 14.4))
    assert phones == {"0035679248232", "0035699859524"}


def test_get_model_spot_fw():
    p = payload(35.9, 14.4, extra_settings={"fw": "G36W_HENG_0.96_LY_F51_V1.0_2021.09.26"})
    assert utils_get_model(p) == "MyKi Spot"


def test_get_model_mode_fallback():
    p = payload(35.9, 14.4, extra_settings={"fw": "XX99_UNKNOWN", "mode": "pet"})
    assert utils_get_model(p) == "MyKi pet tracker"


def test_get_model_generic_fallback():
    p = payload(35.9, 14.4, extra_settings={"fw": ""})
    assert utils_get_model(p) == "MyKi tracker"


def test_gsm_signal():
    p = payload(35.9, 14.4)
    p["current"]["gsmSignalStrength"] = "66"
    assert utils_get_gsm_signal(p) == 66
    assert utils_get_gsm_signal({"current": {}}) is None
