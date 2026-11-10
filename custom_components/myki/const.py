"""Constants for the MyKi integration."""

DOMAIN = "myki"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10  # the vendor app polls every 10 s

PERSONALIZATION_OPTIONS = {
    "profile": {"1": "sound_and_vibration", "2": "sound", "3": "vibration", "4": "mute"},
    "ringtone": {"0": "classic", "1": "playtime", "2": "twinkle"},
    "led": {"0": "off", "1": "on"},
    "flashlight": {"1": "off", "2": "on"},
    "battery_save_mode": {"0": "off", "1": "on"},
    "mode": {"sos": "sos", "pet": "pet", "asset": "asset"},
}

SERVICE_FIND = "find"
SERVICE_MAKE_CALL = "make_call"
ATTR_PHONE = "phone"
