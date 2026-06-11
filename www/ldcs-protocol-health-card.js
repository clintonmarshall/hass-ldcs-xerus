class LdcsProtocolHealthCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 3;
  }

  render() {
    if (!this._hass || !this.config) return;
    const entities = this.config.entities || {};
    const stateObj = (id) => (id && this._hass.states[id] ? this._hass.states[id] : null);
    const state = (id) => stateObj(id)?.state || "unknown";
    const attrs = (id) => stateObj(id)?.attributes || {};
    const samples = entities.telemetrySamples || [];
    const sampleAttrs = samples.map((id) => attrs(id));
    const hasPrometheus = sampleAttrs.some((item) => item.telemetry_source === "prometheus");
    const hasJsonRpc = sampleAttrs.some((item) => item.telemetry_source === "json_rpc") || samples.length > 0;
    const modbusState = state(entities.modbusLayout);
    const modbusAttrs = attrs(entities.modbusLayout);
    const redfishState = state(entities.redfishOutlet);
    const redfishKnown = Boolean(entities.redfishOutlet) && redfishState !== "unknown" && redfishState !== "unavailable";
    const mqttLabel = entities.mqttTopic || "raritan/#";
    const protocols = [
      {
        name: "JSON-RPC",
        detail: hasJsonRpc ? "Discovery, metadata, alarms, extrema" : "Waiting for telemetry",
        state: hasJsonRpc ? "online" : "pending",
        icon: "api",
      },
      {
        name: "Prometheus",
        detail: hasPrometheus ? "Polling matched telemetry samples" : "Fallback to JSON-RPC active",
        state: hasPrometheus ? "online" : "fallback",
        icon: "timeline",
      },
      {
        name: "MQTT Datapush",
        detail: `Refresh trigger ${mqttLabel}`,
        state: "configured",
        icon: "broadcast",
      },
      {
        name: "Redfish",
        detail: redfishKnown ? `Outlet control state: ${redfishState}` : "No controllable outlet entity yet",
        state: redfishKnown ? "online" : "pending",
        icon: "power",
      },
      {
        name: "Modbus/TCP",
        detail: modbusState === "available"
          ? `${modbusAttrs.outlet_count || 0} outlets, ${modbusAttrs.inlet_count || 0} inlets`
          : "Disabled, blocked, or not yet discovered",
        state: modbusState === "available" ? "online" : "optional",
        icon: "registers",
      },
    ];
    const online = protocols.filter((item) => item.state === "online" || item.state === "configured").length;

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          .wrap { padding: 18px; }
          .top { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:16px; }
          .title { font-size:20px; font-weight:750; line-height:1.15; }
          .sub { color:var(--secondary-text-color); font-size:13px; margin-top:5px; }
          .score {
            min-width:78px; border:1px solid rgba(34,197,94,.38); border-radius:8px; padding:10px 12px;
            background:rgba(34,197,94,.08); text-align:center;
          }
          .score b { display:block; font-size:24px; color:#16a34a; }
          .score span { display:block; font-size:11px; color:var(--secondary-text-color); text-transform:uppercase; font-weight:700; }
          .grid { display:grid; grid-template-columns:repeat(5, minmax(0, 1fr)); gap:10px; }
          .protocol {
            border:1px solid rgba(148,163,184,.24); border-radius:8px; padding:12px; min-height:112px;
            background:linear-gradient(180deg, rgba(255,255,255,.045), rgba(2,6,23,.035));
            display:flex; flex-direction:column; justify-content:space-between; gap:12px;
          }
          .badge { width:34px; height:34px; border-radius:8px; display:grid; place-items:center; color:white; background:var(--badge); box-shadow:0 0 16px var(--glow); }
          .name { font-weight:720; font-size:13px; }
          .detail { color:var(--secondary-text-color); font-size:12px; line-height:1.35; min-height:32px; }
          .state { display:inline-flex; align-items:center; gap:6px; font-size:11px; text-transform:uppercase; font-weight:800; color:var(--state); }
          .dot { width:8px; height:8px; border-radius:999px; background:var(--state); box-shadow:0 0 10px var(--state); }
          svg { width:19px; height:19px; stroke:currentColor; stroke-width:2; fill:none; stroke-linecap:round; stroke-linejoin:round; }
          @media (max-width: 980px) { .grid { grid-template-columns:repeat(2, minmax(0, 1fr)); } }
          @media (max-width: 560px) { .top { flex-direction:column; } .grid { grid-template-columns:1fr; } .score { width:100%; box-sizing:border-box; } }
        </style>
        <div class="wrap">
          <div class="top">
            <div>
              <div class="title">${escapeHtml(this.config.title || "LDCS Protocol Health")}</div>
              <div class="sub">How this rack is being discovered, polled, refreshed, and controlled</div>
            </div>
            <div class="score"><b>${online}/${protocols.length}</b><span>active</span></div>
          </div>
          <div class="grid">
            ${protocols.map((item) => protocolTemplate(item)).join("")}
          </div>
        </div>
      </ha-card>
    `;
  }
}

function protocolTemplate(item) {
  const colors = protocolColors(item.state);
  return `
    <div class="protocol" style="--badge:${colors.badge};--glow:${colors.glow};--state:${colors.state}">
      <div>
        <div class="badge">${iconSvg(item.icon)}</div>
      </div>
      <div>
        <div class="name">${escapeHtml(item.name)}</div>
        <div class="detail">${escapeHtml(item.detail)}</div>
      </div>
      <div class="state"><span class="dot"></span>${escapeHtml(item.state)}</div>
    </div>
  `;
}

function protocolColors(state) {
  if (state === "online" || state === "configured") {
    return { badge: "#16a34a", glow: "rgba(22,163,74,.32)", state: "#16a34a" };
  }
  if (state === "fallback") {
    return { badge: "#0ea5e9", glow: "rgba(14,165,233,.3)", state: "#0284c7" };
  }
  if (state === "optional") {
    return { badge: "#64748b", glow: "rgba(100,116,139,.24)", state: "#64748b" };
  }
  return { badge: "#f59e0b", glow: "rgba(245,158,11,.3)", state: "#d97706" };
}

function iconSvg(name) {
  const icons = {
    api: '<svg viewBox="0 0 24 24"><path d="M8 9 5 12l3 3"/><path d="m16 9 3 3-3 3"/><path d="m14 5-4 14"/></svg>',
    timeline: '<svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 5-7"/></svg>',
    broadcast: '<svg viewBox="0 0 24 24"><path d="M4.9 19.1a10 10 0 0 1 0-14.2"/><path d="M8.5 15.5a5 5 0 0 1 0-7"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19.1 4.9a10 10 0 0 1 0 14.2"/><circle cx="12" cy="12" r="1"/></svg>',
    power: '<svg viewBox="0 0 24 24"><path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.8 0"/></svg>',
    registers: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/></svg>',
  };
  return icons[name] || icons.api;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

if (!customElements.get("ldcs-protocol-health-card")) {
  customElements.define("ldcs-protocol-health-card", LdcsProtocolHealthCard);
}
