"""Constants for the Raritan PX4 integration."""

DOMAIN = "raritan_px4"

CONF_VERIFY_SSL = "verify_ssl"
CONF_PROFILE = "profile"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_VERIFY_SSL = False
DEFAULT_PROFILE = "basic"
PROFILES = ["basic", "power", "full"]
MQTT_REFRESH_DEBOUNCE = 2

PLATFORMS = ["button", "sensor", "switch"]
