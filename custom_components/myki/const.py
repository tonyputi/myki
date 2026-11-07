"""Constants for the MyKi integration."""

DOMAIN = "myki"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 10  # the vendor app polls every 10 s

SERVICE_FIND = "find"
SERVICE_MAKE_CALL = "make_call"
ATTR_PHONE = "phone"
