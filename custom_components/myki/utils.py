"""Pure payload helpers (no Home Assistant imports, unit-testable)."""

import json
import math
from typing import Any

AWAY = "Away"


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(a))


def get_position(app_data: dict[str, Any]) -> tuple[float, float, int, str] | None:
    """Return (lat, lon, accuracy_m, position_type) or None if unavailable."""
    pos = (app_data.get("current") or {}).get("position") or {}
    try:
        return (
            float(pos["latitude"]),
            float(pos["longitude"]),
            int(pos.get("accuracy") or 0),
            str(pos.get("type") or ""),
        )
    except (KeyError, TypeError, ValueError):
        return None


def get_zone(app_data: dict[str, Any]) -> str | None:
    """Name of the active safe zone containing the watch, else AWAY."""
    here = get_position(app_data)
    if here is None:
        return None
    lat, lon = here[0], here[1]
    settings = app_data.get("settings") or {}
    for key in sorted(k for k in settings if k.startswith("safe_zone")):
        raw = settings.get(key)
        if not raw:
            continue
        try:
            zone = json.loads(raw)
            if not int(zone.get("active", 0)):
                continue
            # the cloud API stores the radius in kilometers
            if distance_meters(lat, lon, float(zone["lat"]), float(zone["lon"])) <= float(zone["radius"]) * 1000:
                return str(zone.get("name") or key).strip()
        except (ValueError, KeyError, TypeError):
            continue
    return AWAY


def get_battery(app_data: dict[str, Any]) -> int | None:
    """Battery percentage."""
    try:
        return int((app_data.get("current") or {}).get("battery"))
    except (TypeError, ValueError):
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
    except (TypeError, ValueError):
        return None


def authorized_phones(app_data: dict[str, Any]) -> set[str]:
    """All phone numbers the watch is allowed to interact with (SOS + whitelist)."""
    commands = app_data.get("commands") or {}
    phones: set[str] = set()
    for value in commands.values():
        if isinstance(value, str):
            phones.update(p.strip() for p in value.split(",") if p.strip().isdigit())
    return phones
