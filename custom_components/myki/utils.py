"""Pure payload helpers (no Home Assistant imports, unit-testable)."""

import json
import math
from typing import Any

AWAY = "away"


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def get_position(app_data: dict[str, Any]) -> tuple[float, float, int, str] | None:
    """Return (lat, lon, accuracy_m, position_type) or None if unavailable."""
    current = app_data.get("current")
    if not isinstance(current, dict):
        return None
    pos = current.get("position")
    if not isinstance(pos, dict):
        return None
    try:
        lat = float(pos["latitude"])
        lon = float(pos["longitude"])
        accuracy = int(pos.get("accuracy") or 0)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or accuracy < 0:
        return None
    return lat, lon, accuracy, str(pos.get("type") or "")


def get_safe_zones(app_data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return active safe zones, or None if their configuration is invalid."""
    settings = app_data.get("settings")
    if not isinstance(settings, dict):
        return None
    zones = []
    for key in sorted(k for k in settings if k.startswith("safe_zone_")):
        raw = settings[key]
        if raw is None or raw == "":
            continue
        try:
            zone = json.loads(raw)
            if zone is None:
                continue
            if not isinstance(zone, dict):
                return None
            active = zone["active"]
            if active in (0, "0"):
                continue
            if active not in (1, "1"):
                return None
            lat = float(zone["lat"])
            lon = float(zone["lon"])
            radius = float(zone["radius"])
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180 and math.isfinite(radius * 1000) and radius > 0):
            return None
        zones.append(
            {
                "key": key,
                "name": str(zone.get("name") or key).strip() or key,
                "lat": lat,
                "lon": lon,
                # the cloud API stores the radius in kilometers
                "radius_km": radius,
            }
        )
    return zones


def get_zone(app_data: dict[str, Any]) -> str | None:
    """Return the zone or AWAY; invalid position/configuration remains unknown."""
    here = get_position(app_data)
    zones = get_safe_zones(app_data)
    if here is None or zones is None:
        return None
    for zone in zones:
        if distance_meters(here[0], here[1], zone["lat"], zone["lon"]) <= zone["radius_km"] * 1000:
            return zone["name"]
    return AWAY


def get_battery(app_data: dict[str, Any]) -> int | None:
    """Battery percentage."""
    try:
        return int((app_data.get("current") or {}).get("battery"))
    except (TypeError, ValueError, OverflowError):
        return None


def is_online(app_data: dict[str, Any]) -> bool | None:
    """Whether the watch is currently online."""
    raw = (app_data.get("settings") or {}).get("online")
    if raw is None:
        return None
    return str(raw) == "1"


def get_steps_today(app_data: dict[str, Any]) -> int | None:
    """Step count for today."""
    try:
        return int(((app_data.get("current") or {}).get("steps") or {}).get("todaySteps"))
    except (TypeError, ValueError, OverflowError):
        return None


# Known firmware-prefix -> product model map. Verified live unless noted;
# extend only with verified firmware from the device information.
FW_MODELS = {
    "G36W": "MyKi Spot",
}


def get_model(app_data: dict[str, Any]) -> str:
    """Identify verified firmware; a user-selectable mode is not a model."""
    settings = app_data.get("settings") or {}
    fw = str(settings.get("fw") or "")
    for prefix, model in FW_MODELS.items():
        if fw.startswith(prefix):
            return model
    return "MyKi tracker"


def get_gsm_signal(app_data: dict[str, Any]) -> int | None:
    """GSM signal strength in percent."""
    try:
        return int((app_data.get("current") or {}).get("gsmSignalStrength"))
    except (TypeError, ValueError, OverflowError):
        return None
