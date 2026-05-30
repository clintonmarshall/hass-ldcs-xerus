# Security Notes

- Store device credentials only in Home Assistant config entries.
- Do not publish screenshots or exported dashboards containing real IP addresses, serials, or usernames unless intended.
- Redfish outlet switches are operational controls. Restrict dashboard access to trusted Home Assistant users.
- For production, use a dedicated read-only Xerus account for monitoring where possible.
- Use a separate account with control permissions only if outlet switching or reset buttons are required.
- If TLS certificates are not trusted by Home Assistant, `verify_ssl: false` is supported for lab environments.
