"""Optional Modbus/TCP support for Xerus devices."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic

from .const import DEFAULT_MODBUS_PORT, DEFAULT_MODBUS_SLAVE_ID

try:
    from pymodbus.client import ModbusTcpClient
except ImportError:  # pragma: no cover - older pymodbus fallback
    from pymodbus.client.sync import ModbusTcpClient


LAYOUT_CACHE_INTERVAL = 300


@dataclass(frozen=True)
class XerusModbusLayout:
    """Basic Xerus Modbus register layout."""

    register_set_version: str
    register_set_major: int
    register_set_minor: int
    inlet_count: int
    ocp_count: int
    outlet_count: int
    transfer_switch_count: int


class XerusModbusClient:
    """Read optional Xerus Modbus/TCP diagnostics.

    The primary Xerus model remains JSON-RPC/Prometheus. This client is a small
    adapter for BMS-style visibility and future fallback/control work.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_MODBUS_PORT,
        slave_id: int = DEFAULT_MODBUS_SLAVE_ID,
    ) -> None:
        """Initialize the Modbus client."""
        self.host = host
        self.port = port
        self.slave_id = slave_id
        self._lock = Lock()
        self._layout_cache: dict | None = None
        self._last_layout_refresh = 0.0

    def read_layout(self) -> dict:
        """Read and cache the Xerus basic PDU parameter block."""
        with self._lock:
            now = monotonic()
            if self._layout_cache is not None and now - self._last_layout_refresh < LAYOUT_CACHE_INTERVAL:
                return self._layout_cache

            try:
                layout = self._read_layout()
            except Exception as err:  # noqa: BLE001 - pymodbus raises transport-specific errors.
                self._layout_cache = {
                    "available": False,
                    "value": "unavailable",
                    "attributes": {
                        "telemetry_source": "modbus_tcp",
                        "modbus_host": self.host,
                        "modbus_port": self.port,
                        "modbus_slave_id": self.slave_id,
                        "modbus_error": str(err),
                    },
                }
            else:
                self._layout_cache = {
                    "available": True,
                    "value": "available",
                    "attributes": {
                        "telemetry_source": "modbus_tcp",
                        "modbus_host": self.host,
                        "modbus_port": self.port,
                        "modbus_slave_id": self.slave_id,
                        "register_set_version": layout.register_set_version,
                        "register_set_major": layout.register_set_major,
                        "register_set_minor": layout.register_set_minor,
                        "inlet_count": layout.inlet_count,
                        "ocp_count": layout.ocp_count,
                        "outlet_count": layout.outlet_count,
                        "transfer_switch_count": layout.transfer_switch_count,
                        "supported_features": [
                            "basic_pdu_parameters",
                            "inlet_sensor_registers",
                            "ocp_sensor_registers",
                            "outlet_sensor_registers",
                            "outlet_relay_coils",
                            "peripheral_sensor_registers",
                            "transfer_switch_registers",
                        ],
                    },
                }
            self._last_layout_refresh = now
            return self._layout_cache

    def _read_layout(self) -> XerusModbusLayout:
        client = ModbusTcpClient(self.host, port=self.port, timeout=3)
        try:
            if not client.connect():
                raise ConnectionError("Unable to connect to Xerus Modbus/TCP service")
            response = _modbus_call(client.read_holding_registers, 0x0000, 5, self.slave_id)
            if _is_error(response):
                raise ConnectionError("Unable to read Xerus basic Modbus parameter block")
            version = response.registers[0]
            major = (version >> 8) & 0xFF
            minor = version & 0xFF
            return XerusModbusLayout(
                register_set_version=f"{major}.{minor}",
                register_set_major=major,
                register_set_minor=minor,
                inlet_count=response.registers[1],
                ocp_count=response.registers[2],
                outlet_count=response.registers[3],
                transfer_switch_count=response.registers[4],
            )
        finally:
            client.close()


def _modbus_call(method, address: int, count: int, slave_id: int):
    """Call pymodbus across recent keyword variants."""
    try:
        return method(address=address, count=count, slave=slave_id)
    except TypeError:
        return method(address=address, count=count, device_id=slave_id)


def _is_error(response) -> bool:
    return response is None or (hasattr(response, "isError") and response.isError())
