"""Minimal Redfish client for Raritan Xerus devices."""

from __future__ import annotations

from dataclasses import dataclass

import requests
from urllib3.exceptions import InsecureRequestWarning


@dataclass(frozen=True)
class RedfishOutlet:
    """A switchable Redfish outlet."""

    outlet_id: str
    name: str
    target: str


class RedfishClient:
    """Follow the Raritan Redfish PowerEquipment links."""

    def __init__(self, host, username, password, verify_ssl=False):
        """Initialize the Redfish client."""
        self.base_url = f"https://{host}"
        self.auth = (username, password)
        self.verify_ssl = verify_ssl
        self.outlets: list[RedfishOutlet] = []
        if not verify_ssl:
            requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

    def discover_outlets(self):
        """Return switchable outlets advertised by the PDU."""
        rack_pdus = self._get("/redfish/v1/PowerEquipment/RackPDUs")
        members = rack_pdus.get("Members", [])
        if not members:
            return []

        pdu = self._get(members[0]["@odata.id"])
        outlets_link = pdu.get("Outlets", {}).get("@odata.id")
        if not outlets_link:
            return []

        outlets = []
        collection = self._get(outlets_link)
        for member in collection.get("Members", []):
            outlet = self._get(member["@odata.id"])
            target = (
                outlet.get("Actions", {})
                .get("#Outlet.PowerControl", {})
                .get("target")
            )
            if not target:
                continue
            outlet_id = str(outlet.get("Id") or member["@odata.id"].rstrip("/").split("/")[-1])
            name = outlet.get("UserLabel") or outlet.get("Name") or f"Outlet {outlet_id}"
            outlets.append(RedfishOutlet(outlet_id=outlet_id, name=name, target=target))
        self.outlets = outlets
        return outlets

    def set_outlet_power(self, target, state):
        """Set an outlet power state."""
        response = requests.post(
            self._url(target),
            json={"PowerState": "On" if state else "Off"},
            auth=self.auth,
            verify=self.verify_ssl,
            timeout=10,
        )
        response.raise_for_status()

    def _get(self, path):
        response = requests.get(
            self._url(path),
            auth=self.auth,
            verify=self.verify_ssl,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _url(self, path):
        return path if path.startswith("http") else f"{self.base_url}{path}"
