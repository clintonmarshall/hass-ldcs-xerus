"""USystems RDHx Modbus profile for LDCS."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL

from .const import (
    CONF_MODBUS_PORT,
    CONF_MODBUS_SLAVE_ID,
    DEFAULT_MODBUS_PORT,
    DEFAULT_MODBUS_SLAVE_ID,
    DOMAIN,
)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - older pymodbus fallback
    from pymodbus.client.sync import ModbusTcpClient


@dataclass(frozen=True)
class RdhxRegister:
    """USystems RDHx register description."""

    key: str
    name: str
    address: int
    register_type: str
    data_type: str = "int16"
    scale: float | None = None
    precision: int | None = 2
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None


@dataclass(frozen=True)
class RdhxBinaryRegister:
    """USystems RDHx discrete input description."""

    key: str
    name: str
    address: int
    device_class: str | None = None


RDHX_SENSORS: tuple[RdhxRegister, ...] = (
    RdhxRegister("air_off_coil_temperature", "Air Off Coil Temperature", 1, "input", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("air_on_coil_temperature", "Air On Coil Temperature", 2, "input", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("cabinet_front_room_temperature", "Cabinet Front Room Temperature", 3, "input", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("fan_2_requested_speed", "Fan 2 Requested Speed", 5, "input", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("fan_2_command", "Fan 2 Command", 23, "input", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("fan_2_expected_feedback_raw", "Fan 2 Expected Feedback Raw", 11, "input", state_class="measurement"),
    RdhxRegister("fan_2_feedback_raw", "Fan 2 Feedback Raw", 17, "input", state_class="measurement"),
    RdhxRegister("valve_request", "Valve Request", 22, "input", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("valve_feedback", "Valve Feedback", 58, "input", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("analog_output_2", "Analog Output 2", 24, "input", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("alternative_air_on_temperature", "Alternative Air On Temperature", 256, "input", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("alternative_air_off_temperature", "Alternative Air Off Temperature", 257, "input", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("return_water_tqs3_temperature_raw", "Return Water / TQS3 Temperature Raw", 258, "input"),
    RdhxRegister("alarm_word", "Alarm Word", 150, "input"),
    RdhxRegister("warning_word", "Warning Word", 151, "input"),
    RdhxRegister("warning_word_2", "Warning Word 2", 152, "input"),
    RdhxRegister("clock_seconds", "Clock Seconds", 177, "input", data_type="uint16"),
    RdhxRegister("clock_minutes", "Clock Minutes", 178, "input", data_type="uint16"),
    RdhxRegister("clock_hours", "Clock Hours", 179, "input", data_type="uint16"),
    RdhxRegister("clock_day", "Clock Day", 180, "input", data_type="uint16"),
    RdhxRegister("clock_month", "Clock Month", 181, "input", data_type="uint16"),
    RdhxRegister("clock_year", "Clock Year", 182, "input", data_type="uint16"),
    RdhxRegister("unit_lifetime", "Unit Lifetime", 183, "input", data_type="uint32", unit="h", state_class="total_increasing"),
    RdhxRegister("fan_setpoint", "Fan Setpoint", 25, "holding", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("fan_differential", "Fan Differential", 26, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("zone_2_setpoint", "Zone 2 Setpoint", 27, "holding", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("zone_2_differential", "Zone 2 Differential", 28, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("valve_setpoint", "Valve Setpoint", 29, "holding", scale=0.1, precision=1, unit="°C", device_class="temperature", state_class="measurement"),
    RdhxRegister("reduced_valve_differential", "Reduced Valve Differential", 30, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("valve_differential", "Valve Differential", 31, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("valve_minimum_opening", "Valve Minimum Opening", 32, "holding", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("valve_maximum_opening", "Valve Maximum Opening", 33, "holding", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("fan_minimum_speed", "Fan Minimum Speed", 42, "holding", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("fan_maximum_speed", "Fan Maximum Speed", 43, "holding", scale=0.1, precision=1, unit="%", state_class="measurement"),
    RdhxRegister("fan_cut_off_differential", "Fan Cut Off Differential", 44, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("high_temperature_alarm_differential", "High Temperature Alarm Differential", 45, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
    RdhxRegister("low_temperature_alarm_differential", "Low Temperature Alarm Differential", 46, "holding", scale=0.1, precision=1, unit="K", state_class="measurement"),
)

RDHX_BINARY_SENSORS: tuple[RdhxBinaryRegister, ...] = (
    RdhxBinaryRegister("unit_on", "Unit On", 3),
    RdhxBinaryRegister("global_alarm", "Global Alarm", 4, "problem"),
    RdhxBinaryRegister("dout_01_status", "DOUT 01 Status", 5),
    RdhxBinaryRegister("dout_02_status", "DOUT 02 Status", 6),
    RdhxBinaryRegister("dout_03_status", "DOUT 03 Status", 7),
    RdhxBinaryRegister("dout_04_status", "DOUT 04 Status", 8),
    RdhxBinaryRegister("dout_05_status", "DOUT 05 Status", 9),
    RdhxBinaryRegister("dout_06_status", "DOUT 06 Status", 10),
    RdhxBinaryRegister("leak_alarm", "Leak Alarm", 63, "problem"),
    RdhxBinaryRegister("fan_2_speed_alarm", "Fan 2 Speed Alarm", 65, "problem"),
    RdhxBinaryRegister("air_off_sensor_broken_alarm", "Air Off Sensor Broken Alarm", 75, "problem"),
    RdhxBinaryRegister("air_on_sensor_broken_alarm", "Air On Sensor Broken Alarm", 76, "problem"),
    RdhxBinaryRegister("high_temperature_zone_1_alarm", "High Temperature Zone 1 Alarm", 77, "problem"),
    RdhxBinaryRegister("high_temperature_zone_2_alarm", "High Temperature Zone 2 Alarm", 78, "problem"),
    RdhxBinaryRegister("low_temperature_zone_1_alarm", "Low Temperature Zone 1 Alarm", 79, "problem"),
    RdhxBinaryRegister("low_temperature_zone_2_alarm", "Low Temperature Zone 2 Alarm", 80, "problem"),
    RdhxBinaryRegister("coil_clean_warning", "Coil Clean Warning", 86, "problem"),
    RdhxBinaryRegister("fan_check_warning", "Fan Check Warning", 87, "problem"),
    RdhxBinaryRegister("filter_clean_warning", "Filter Clean Warning", 88, "problem"),
    RdhxBinaryRegister("service_warning", "Service Warning", 89, "problem"),
    RdhxBinaryRegister("valve_check_warning", "Valve Check Warning", 90, "problem"),
    RdhxBinaryRegister("valve_feedback_alarm", "Valve Feedback Alarm", 128, "problem"),
    RdhxBinaryRegister("fan_global_alarm", "Fan Global Alarm", 150, "problem"),
    RdhxBinaryRegister("high_air_off_temperature_alarm", "High Air Off Temperature Alarm", 157, "problem"),
    RdhxBinaryRegister("low_air_off_temperature_alarm", "Low Air Off Temperature Alarm", 158, "problem"),
    RdhxBinaryRegister("leak_alarm_din02_enabled", "Leak Alarm DIN02 Enabled", 168),
)


class USystemsRdhxClient:
    """Read a USystems RDHx Modbus TCP device."""

    def __init__(self, entry_data: dict):
        """Initialize the client from a config entry."""
        self.host = entry_data[CONF_HOST]
        self.port = entry_data.get(CONF_MODBUS_PORT, DEFAULT_MODBUS_PORT)
        self.slave_id = entry_data.get(CONF_MODBUS_SLAVE_ID, DEFAULT_MODBUS_SLAVE_ID)
        self.scan_interval = entry_data.get(CONF_SCAN_INTERVAL)
        self._lock = Lock()

    @property
    def device_info(self) -> dict:
        """Return Home Assistant device info."""
        identifier = f"usystems_rdhx_{self.host}_{self.port}_{self.slave_id}"
        return {
            "identifiers": {(DOMAIN, identifier)},
            "manufacturer": "Legrand",
            "model": "USystems RDHx",
            "name": f"USystems RDHx {self.host}",
            "configuration_url": f"http://{self.host}",
        }

    def update(self) -> dict:
        """Read configured RDHx registers."""
        with self._lock:
            client = ModbusTcpClient(self.host, port=self.port, timeout=5)
            try:
                if not client.connect():
                    return {}
                data = {}
                for register in RDHX_SENSORS:
                    data[register.key] = self._read_register(client, register)
                for register in RDHX_BINARY_SENSORS:
                    data[register.key] = self._read_discrete(client, register)
                return data
            finally:
                client.close()

    def _read_register(self, client, register: RdhxRegister) -> dict:
        count = 2 if register.data_type == "uint32" else 1
        method = client.read_holding_registers if register.register_type == "holding" else client.read_input_registers
        response = _modbus_call(method, register.address, count, self.slave_id)
        if _is_error(response):
            return {"available": False, "value": None}
        value = _decode_registers(response.registers, register.data_type)
        if register.scale is not None:
            value *= register.scale
        if register.precision is not None:
            value = round(value, register.precision)
        return {"available": True, "value": value}

    def _read_discrete(self, client, register: RdhxBinaryRegister) -> dict:
        response = _modbus_call(client.read_discrete_inputs, register.address, 1, self.slave_id)
        if _is_error(response):
            return {"available": False, "value": None}
        return {"available": True, "value": bool(response.bits[0])}


def _modbus_call(method, address: int, count: int, slave_id: int):
    """Call pymodbus across recent keyword variants."""
    try:
        return method(address=address, count=count, slave=slave_id)
    except TypeError:
        return method(address=address, count=count, device_id=slave_id)


def _is_error(response) -> bool:
    return response is None or (hasattr(response, "isError") and response.isError())


def _decode_registers(registers: list[int], data_type: str) -> int:
    if data_type == "uint32":
        return (registers[1] << 16) + registers[0]
    raw = registers[0]
    if data_type == "int16" and raw >= 0x8000:
        return raw - 0x10000
    return raw
