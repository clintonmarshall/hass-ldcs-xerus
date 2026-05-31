"""Constants for the Legrand Data Center Solutions integration."""

DOMAIN = "ldcs"

CONF_CREATE_DASHBOARD = "create_dashboard"
CONF_MODBUS_PORT = "modbus_port"
CONF_MODBUS_SLAVE_ID = "modbus_slave_id"
CONF_VERIFY_SSL = "verify_ssl"
CONF_PROFILE = "profile"
CONF_PRODUCT_TYPE = "product_type"
CONF_RACK_NAME = "rack_name"
CONF_RACK_POSITION = "rack_position"
CONF_RACK_ROLE = "rack_role"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_MODBUS_PORT = 502
DEFAULT_MODBUS_SLAVE_ID = 1
DEFAULT_VERIFY_SSL = False
DEFAULT_PROFILE = "basic"
DEFAULT_PRODUCT_TYPE = "xerus_pdu"
DEFAULT_RACK_NAME = "Rack 01"
DEFAULT_CREATE_DASHBOARD = False
PROFILES = ["basic", "power", "full"]
PRODUCT_XERUS_PDU = "xerus_pdu"
PRODUCT_USYSTEMS_RDHX = "usystems_rdhx"
PRODUCT_RACK_DASHBOARD = "rack_dashboard"
PRODUCT_TYPES = [PRODUCT_XERUS_PDU, PRODUCT_USYSTEMS_RDHX, PRODUCT_RACK_DASHBOARD]
RACK_ROLES = ["left_pdu", "right_pdu", "cooling", "busway", "sensor_strip", "rack"]
MQTT_REFRESH_DEBOUNCE = 2

PLATFORMS = ["button", "sensor", "switch"]
