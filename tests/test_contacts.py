"""Spot app contact formats and validation; no private fixtures."""

import pytest

from custom_components.myki.api import MykiError
from custom_components.myki.contacts import CONTACT_SLOTS, contact_numbers, normalize_phone


def test_slots_and_hidden_whitelist_values():
    contacts = contact_numbers({"commands": {"sos_phone_1": "+15555550100", "volume_ring": "4", "interval": "120", "whitelist_2": ",0015555550101,0015555550102,,0015555550103"}})
    assert len(CONTACT_SLOTS) == 10
    assert len(contacts) == 13
    assert contacts["sos_1"] == "+15555550100"
    assert contacts["whitelist_6"] == ""
    assert contacts["whitelist_7"] == "0015555550101"
    assert contacts["whitelist_8"] == "0015555550102"
    assert contacts["whitelist_10"] == "0015555550103"


@pytest.mark.parametrize("value,expected", [("", ""), ("+15555550100", "0015555550100"), ("0015555550100", "0015555550100"), ("5550100", "5550100")])
def test_normalization(value, expected):
    assert normalize_phone(value) == expected


@pytest.mark.parametrize("value", [None, 123, "+", "++123", "123&x=1", "１２３", "123,456", "123 456"])
def test_reject_invalid_numbers(value):
    with pytest.raises(MykiError):
        normalize_phone(value)


@pytest.mark.parametrize("commands", [{"sos_phone_1": None}, {"whitelist_1": []}, {"whitelist_2": ",,,,,"}, {"whitelist_1": "123,invalid"}])
def test_malformed_contact_data_is_not_silently_replaced(commands):
    with pytest.raises(MykiError):
        contact_numbers({"commands": commands})
