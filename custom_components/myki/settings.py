"""App-format settings validation; never synthesize missing cloud schedules."""

from copy import deepcopy
import json
import math
import re
from typing import Any

WEEKDAYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")
DISABLED_PERIOD = "00:00-00:00"
TIME_PATTERN = r"(?:[01][0-9]|2[0-3]):[0-5][0-9]"


def scalar_setting(app: dict, key: str) -> str:
    """Match the app's settings/commands locations, not a local preference."""
    section = "settings" if key in ("mode", "battery_save_mode") else "commands"
    field = "led" if key == "flashlight" else key
    return str((app.get(section) or {}).get(field))


def validate_zone(value: dict) -> dict:
    """Validate the app fields while retaining all unknown cloud keys."""
    if not isinstance(value, dict) or not isinstance(value.get("name"), str) or not value["name"].strip() or len(value["name"]) > 255:
        raise ValueError("invalid safe-zone name")
    for field, minimum, maximum in (("lat", -90, 90), ("lon", -180, 180), ("radius", 0, math.inf)):
        raw = value.get(field)
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            raise ValueError("invalid safe-zone coordinates or radius")
        try:
            number = float(raw)
        except (ValueError, OverflowError):
            raise ValueError("invalid safe-zone coordinates or radius") from None
        if not math.isfinite(number) or not minimum <= number <= maximum or (field == "radius" and (number == 0 or not math.isfinite(number * 1000))):
            raise ValueError("invalid safe-zone coordinates or radius")
    if str(value.get("active")) not in ("0", "1") or str(value.get("profile")) not in ("1", "2", "3", "4"):
        raise ValueError("invalid safe-zone activation or ring mode")
    return value


def read_group(app: dict, key: str) -> dict | list[str]:
    """Decode two official zones or complete command groups; reject malformed data."""
    section = "settings" if key in ("safe_zone_1", "safe_zone_2") else "commands"
    raw = (app.get(section) or {}).get(key)
    if key in ("safe_zone_1", "safe_zone_2"):
        if raw in (None, ""):
            return {}
        if not isinstance(raw, str):
            raise ValueError("invalid safe-zone data")
        try:
            zone = json.loads(raw)
        except (ValueError, TypeError):
            raise ValueError("invalid safe-zone data") from None
        return validate_zone(zone)
    if not isinstance(raw, str):
        raise ValueError("schedule is missing; refresh before editing")
    values = raw.split(",")
    validate_group(key, values)
    return values


def validate_group(key: str, values: list[str]) -> None:
    """Alarms retain the app's opaque digit at offset 8, including disabled slots."""
    if key == "silencetime":
        pattern, count = f"{TIME_PATTERN}-{TIME_PATTERN}", 4
    elif key == "remind":
        pattern, count = f"{TIME_PATTERN}-[01]-[0-9]-[01]{{7}}", 3
    else:
        raise ValueError("invalid schedule")
    if not isinstance(values, list) or len(values) != count or any(
        not isinstance(value, str) or not re.fullmatch(pattern, value) for value in values
    ):
        raise ValueError("invalid schedule data")


def edit_group(key: str, current: dict | list[str], changes: dict[str, Any], index: int | None) -> dict | list[str]:
    """Apply structured edits to a fresh group, preserving siblings and opaque fields."""
    result = deepcopy(current)
    if key in ("safe_zone_1", "safe_zone_2"):
        if index is not None or not changes or set(changes) - {"name", "latitude", "longitude", "radius", "enabled", "ring_mode"}:
            raise ValueError("invalid safe-zone edit")
        mapping = {"latitude": "lat", "longitude": "lon", "radius": "radius", "enabled": "active", "ring_mode": "profile", "name": "name"}
        for field, value in changes.items():
            if field == "enabled":
                if not isinstance(value, bool):
                    raise ValueError("enabled must be a boolean")
                value = int(value)
            elif field == "ring_mode":
                if str(value) not in ("1", "2", "3", "4"):
                    raise ValueError("invalid safe-zone ring mode")
                value = int(value)
            elif field == "radius":
                if isinstance(value, bool) or not isinstance(value, (float, int)):
                    raise ValueError("radius must be a number in meters")
                try:
                    value = float(value) / 1000
                except OverflowError:
                    raise ValueError("invalid safe-zone radius") from None
            result[mapping[field]] = value
        return validate_zone(result)
    if isinstance(index, bool) or not isinstance(index, int) or not isinstance(result, list) or not 0 <= index < len(result) or not changes:
        raise ValueError("invalid schedule slot")
    if key == "silencetime":
        if index != 0 or set(changes) - {"enabled", "start", "end"} or not isinstance(changes.get("enabled"), bool):
            raise ValueError("invalid DND edit")
        if changes["enabled"]:
            start, end = result[0].split("-")
            start, end = changes.get("start", start), changes.get("end", end)
            if not isinstance(start, str) or not isinstance(end, str) or not re.fullmatch(TIME_PATTERN, start) or not re.fullmatch(TIME_PATTERN, end) or start == end:
                raise ValueError("DND needs distinct HH:MM start/end times")
            result[0] = f"{start}-{end}"
        else:
            result[0] = DISABLED_PERIOD
    elif key == "remind":
        if set(changes) - {"enabled", "time", "weekdays"}:
            raise ValueError("invalid alarm edit")
        alarm = result[index]
        if "time" in changes:
            if not isinstance(changes["time"], str) or not re.fullmatch(TIME_PATTERN, changes["time"]):
                raise ValueError("alarm time must be HH:MM")
            alarm = changes["time"] + alarm[5:]
        if "enabled" in changes:
            if not isinstance(changes["enabled"], bool):
                raise ValueError("enabled must be a boolean")
            alarm = alarm[:6] + str(int(changes["enabled"])) + alarm[7:]
        if "weekdays" in changes:
            days = changes["weekdays"]
            if not isinstance(days, list) or any(not isinstance(day, str) or day not in WEEKDAYS for day in days) or len(set(days)) != len(days):
                raise ValueError("invalid alarm weekdays")
            alarm = alarm[:10] + "".join("1" if day in days else "0" for day in WEEKDAYS)
        if alarm[6] == "1" and "1" not in alarm[10:17]:
            raise ValueError("an enabled alarm needs at least one weekday")
        result[index] = alarm
    else:
        raise ValueError("invalid schedule")
    validate_group(key, result)
    return result
