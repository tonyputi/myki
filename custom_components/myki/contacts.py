"""Contact slots used by the Spot app, including hidden whitelist preservation."""

import re

from .api import MykiError

CONTACT_SLOTS = tuple(f"sos_{i}" for i in range(1, 4)) + tuple(f"whitelist_{i}" for i in range(1, 8))


def normalize_phone(value: str) -> str:
    """Compare international prefixes without guessing a country code."""
    if not isinstance(value, str) or not re.fullmatch(r"\+?[0-9]*", value) or value == "+":
        raise MykiError("invalid contact number")
    return "00" + value[1:] if value.startswith("+") else value


def contact_numbers(app: dict) -> dict[str, str]:
    """Decode all stored slots; malformed groups must never be overwritten."""
    commands = app.get("commands") or {}
    contacts = {}
    for i in range(1, 4):
        value = commands.get(f"sos_phone_{i}", "")
        normalize_phone(value)
        contacts[f"sos_{i}"] = value
    for group in (1, 2):
        raw = commands.get(f"whitelist_{group}", "")
        if not isinstance(raw, str):
            raise MykiError("invalid contact group")
        values = raw.split(",") if raw else []
        if len(values) > 5:
            raise MykiError("invalid contact group")
        values += [""] * (5 - len(values))
        for index, value in enumerate(values, start=(group - 1) * 5 + 1):
            normalize_phone(value)
            contacts[f"whitelist_{index}"] = value
    return contacts
