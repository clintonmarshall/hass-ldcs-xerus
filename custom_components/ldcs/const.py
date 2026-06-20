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
CONF_XERUS_TOPOLOGY = "xerus_topology"
CONF_XERUS_MQTT_DATAPUSH = "xerus_mqtt_datapush"
CONF_XERUS_MQTT_HOST = "xerus_mqtt_host"
CONF_XERUS_MQTT_PORT = "xerus_mqtt_port"
CONF_XERUS_MQTT_TLS = "xerus_mqtt_tls"
CONF_XERUS_MQTT_USERNAME = "xerus_mqtt_username"
CONF_XERUS_MQTT_PASSWORD = "xerus_mqtt_password"
CONF_XERUS_MQTT_TOPIC_PREFIX = "xerus_mqtt_topic_prefix"
CONF_XERUS_DEVICE_FAMILY = "xerus_device_family"
CONF_XERUS_CAPABILITIES = "xerus_capabilities"
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_MODBUS_PORT = 502
DEFAULT_MODBUS_SLAVE_ID = 1
DEFAULT_VERIFY_SSL = False
DEFAULT_PROFILE = "basic"
DEFAULT_PRODUCT_TYPE = "xerus_pdu"
DEFAULT_RACK_NAME = "Rack 01"
DEFAULT_CREATE_DASHBOARD = False
DEFAULT_XERUS_TOPOLOGY = "pdu_link_master"
DEFAULT_XERUS_MQTT_DATAPUSH = False
DEFAULT_XERUS_MQTT_PORT = 1883
DEFAULT_XERUS_MQTT_TLS = False
PROFILES = ["basic", "power", "full"]
PRODUCT_XERUS_PDU = "xerus_pdu"
PRODUCT_USYSTEMS_RDHX = "usystems_rdhx"
PRODUCT_RACK_DASHBOARD = "rack_dashboard"
PRODUCT_TYPES = [PRODUCT_XERUS_PDU, PRODUCT_USYSTEMS_RDHX, PRODUCT_RACK_DASHBOARD]
RACK_ROLES = ["left_pdu", "right_pdu", "cooling", "busway", "sensor_strip", "rack"]
XERUS_TOPOLOGIES = ["pdu_link_master", "standalone", "separate_rack_pdu"]
MQTT_REFRESH_DEBOUNCE = 2

XERUS_PLATFORMS = ["button", "sensor", "switch"]
USYSTEMS_RDHX_PLATFORMS = ["binary_sensor", "sensor"]
PLATFORMS = sorted({*XERUS_PLATFORMS, *USYSTEMS_RDHX_PLATFORMS})
