class LdcsRackStatusCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 6;
  }

  render() {
    if (!this._hass || !this.config) return;
    const e = this.config.entities || {};
    const alarms = ids(e.alarms).map((id) => this.stateObj(id)).filter(Boolean);
    const ocps = ids(e.ocpStates).map((id) => this.stateObj(id)).filter(Boolean);
    const outlets = ids(e.outletStates).map((id) => this.stateObj(id)).filter(Boolean);
    const assetInventories = ids(e.assetInventories).map((id) => attrs(this._hass, id));
    const powerEntities = ids(e.rackPower).map((id) => this.stateObj(id)).filter(Boolean);
    const currentEntities = ids(e.phaseCurrent || e.inletCurrent).map((id) => this.stateObj(id)).filter(Boolean);
    const doors = ids(e.doorStates).map((id) => this.stateObj(id)).filter(Boolean);
    const locks = ids(e.lockStates).map((id) => this.stateObj(id)).filter(Boolean);
    const controls = ids(e.controllableStates).map((id) => this.stateObj(id)).filter(Boolean);
    const service = this.stateObj(e.serviceStatus);
    const security = this.stateObj(e.securityStatus);

    const alarmScore = alarmNumber(alarms, "acknowledgement_required_alarm_count")
      + alarmNumber(alarms, "active_breach_count")
      + alarmNumber(alarms, "critical_count")
      + alarmNumber(alarms, "warning_count");
    const activeAlarms = Math.max(0, alarmScore);
    const ocpCounts = countStates(ocps, {
      tripped: ["trip", "tripped", "on", "true", "1", "critical"],
      normal: ["normal", "closed", "off", "false", "0", "ok"],
    });
    const outletCounts = countStates(outlets, {
      on: ["on", "true", "closed", "power on"],
      off: ["off", "false", "open", "power off"],
      service: ["service", "maintenance"],
      loadshed: ["load shed", "loadshed", "shed"],
      cycling: ["cycle", "cycling", "reboot"],
    });
    const assetTags = assetInventories.flatMap((inventory) => inventory.asset_tags || []);
    const totalPower = sumNumeric(powerEntities);
    const pduBalance = balanceByPdu(powerEntities);
    const phaseBalance = balanceByPhase(currentEntities);
    const balance = phaseBalance.available ? phaseBalance : pduBalance;
    const doorOpen = doors.some((item) => isDoorOpen(item.state));
    const unlocked = locks.some((item) => isUnlocked(item.state));
    const health = activeAlarms > 0 || ocpCounts.tripped > 0
      ? "alarm"
      : doorOpen || unlocked
        ? "attention"
        : "normal";

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          .wrap { padding:18px; }
          .head { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:16px; }
          .title { font-size:20px; font-weight:750; }
          .sub { color:var(--secondary-text-color); font-size:13px; margin-top:4px; }
          .health { min-width:116px; text-align:center; border-radius:8px; padding:10px 12px; color:white; font-weight:800; text-transform:uppercase; letter-spacing:.04em; background:${healthColor(health)}; box-shadow:0 0 18px ${healthGlow(health)}; }
          .scanner { height:10px; border-radius:999px; background:rgba(148,163,184,.22); overflow:hidden; margin:12px 0 18px; position:relative; }
          .scanner:before { content:""; position:absolute; width:34%; inset:0 auto 0 0; border-radius:999px; background:linear-gradient(90deg, transparent, ${healthColor(health)}, transparent); animation:scan 1.45s linear infinite; }
          @keyframes scan { 0%{ transform:translateX(-100%); } 100%{ transform:translateX(300%); } }
          .grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
          .tile { border:1px solid rgba(148,163,184,.22); border-radius:8px; padding:12px; background:rgba(255,255,255,.04); min-width:0; }
          .tile span { display:flex; gap:6px; align-items:center; color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; font-weight:800; }
          .tile b { display:block; margin-top:7px; font-size:24px; line-height:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .tile small { display:block; margin-top:7px; color:var(--secondary-text-color); line-height:1.35; }
          .dot { width:9px; height:9px; border-radius:999px; display:inline-block; background:var(--dot); box-shadow:0 0 10px var(--dot); }
          .wide { grid-column:span 2; }
          .bar { height:9px; border-radius:999px; background:rgba(148,163,184,.22); overflow:hidden; margin-top:8px; }
          .bar i { display:block; height:100%; width:var(--w); background:${balance.color}; }
          @media (max-width: 900px) { .grid { grid-template-columns:1fr 1fr; } .wide { grid-column:span 2; } }
          @media (max-width: 620px) { .head { flex-direction:column; } .grid { grid-template-columns:1fr; } .wide { grid-column:auto; } }
        </style>
        <div class="wrap">
          <div class="head">
            <div>
              <div class="title">${escapeHtml(this.config.title || "Rack Status")}</div>
              <div class="sub">${service ? escapeHtml(service.state) : "Live rack health, load, security, and inventory"}</div>
            </div>
            <div class="health">${health}</div>
          </div>
          <div class="scanner"></div>
          <div class="grid">
            ${tile("Alarms", activeAlarms, activeAlarms ? "Active alarm or threshold breach" : "No active alarm count reported", activeAlarms ? "#ef4444" : "#22c55e")}
            ${tile("OCP / breakers", `${ocpCounts.total}`, `${ocpCounts.tripped} tripped, ${ocpCounts.normal} normal`, ocpCounts.tripped ? "#ef4444" : "#22c55e")}
            ${tile("Outlets", `${outletCounts.total}`, `${outletCounts.on} on, ${outletCounts.off} off, ${outletCounts.service} service, ${outletCounts.loadshed} load shed`, "#38bdf8")}
            ${tile("Asset tags", assetTags.length, "Detected on rack asset strips", assetTags.length ? "#22c55e" : "#94a3b8")}
            ${tile("Rack power", formatWatts(totalPower), `${powerEntities.length} rack/inlet power sensors`, totalPower > 0 ? "#f59e0b" : "#94a3b8")}
            ${tile("Doors / locks", doorOpen ? "Open" : unlocked ? "Unlocked" : "Secure", `${doors.length} door sensors, ${locks.length} lock/handle sensors`, doorOpen || unlocked ? "#f59e0b" : "#22c55e")}
            ${tile("Controls", controls.length, "Writable handle, lock, or dry-contact switches", controls.length ? "#38bdf8" : "#94a3b8")}
            <div class="tile wide">
              <span><i class="dot" style="--dot:${balance.color}"></i>${escapeHtml(balance.label)}</span>
              <b>${balance.available ? `${balance.imbalance.toFixed(1)}%` : "--"}</b>
              <small>${escapeHtml(balance.detail)}</small>
              <div class="bar" style="--w:${Math.max(2, Math.min(100, balance.imbalance || 0))}%"><i></i></div>
            </div>
            ${tile("Security", security ? security.state : "unknown", "Rack security summary", security && security.state !== "normal" ? "#f59e0b" : "#22c55e")}
          </div>
        </div>
      </ha-card>
    `;
  }

  stateObj(entityId) {
    return entityId && this._hass.states[entityId] ? this._hass.states[entityId] : null;
  }
}

function ids(value) {
  if (!value) return [];
  return Array.isArray(value) ? value.filter(Boolean) : [value];
}

function attrs(hass, entityId) {
  return entityId && hass.states[entityId] ? hass.states[entityId].attributes || {} : {};
}

function lower(value) {
  return String(value ?? "").toLowerCase();
}

function isDoorOpen(value) {
  const raw = lower(value);
  return raw === "0" || raw === "false" || raw.includes("open");
}

function isUnlocked(value) {
  const raw = lower(value);
  return raw === "0" || raw === "false" || raw.includes("unlock") || raw.includes("open");
}

function countStates(items, groups) {
  const result = { total: items.length };
  for (const key of Object.keys(groups)) result[key] = 0;
  for (const item of items) {
    const value = lower(item.state);
    for (const [key, needles] of Object.entries(groups)) {
      if (needles.some((needle) => value.includes(needle))) {
        result[key] += 1;
        break;
      }
    }
  }
  return result;
}

function alarmNumber(items, attrName) {
  let total = 0;
  for (const item of items) {
    if (!lower(item.entity_id).includes(attrName) && !lower(item.entity_id).includes(attrName.replace(/_/g, ""))) continue;
    const value = Number.parseFloat(item.state);
    if (Number.isFinite(value)) total += value;
  }
  return total;
}

function sumNumeric(items) {
  return items.reduce((sum, item) => {
    const value = Number.parseFloat(item.state);
    return sum + (Number.isFinite(value) ? value : 0);
  }, 0);
}

function balanceByPdu(items) {
  const totals = { a: 0, b: 0 };
  for (const item of items) {
    const value = Number.parseFloat(item.state);
    if (!Number.isFinite(value)) continue;
    const id = lower(item.entity_id);
    if (id.includes("pdu_b")) totals.b += value;
    else totals.a += value;
  }
  const values = Object.values(totals).filter((value) => value > 0);
  return balanceFromValues(values, "PDU load balance", "Compares total load between PDU A and PDU B");
}

function balanceByPhase(items) {
  const phases = {};
  for (const item of items) {
    const value = Number.parseFloat(item.state);
    if (!Number.isFinite(value)) continue;
    const attrLine = lower(item.attributes?.power_line || "");
    const id = lower(item.entity_id);
    const line = attrLine || (id.includes("_l1_") ? "l1" : id.includes("_l2_") ? "l2" : id.includes("_l3_") ? "l3" : "");
    if (!line) continue;
    phases[line.toUpperCase()] = (phases[line.toUpperCase()] || 0) + value;
  }
  return balanceFromValues(Object.values(phases).filter((value) => value > 0), "Phase balance", "Compares L1/L2/L3 current when phase sensors are available");
}

function balanceFromValues(values, label, detail) {
  if (values.length < 2) {
    return { available: false, label, detail: "Not enough comparable load points are available yet", imbalance: 0, color: "#94a3b8" };
  }
  const max = Math.max(...values);
  const min = Math.min(...values);
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const imbalance = avg ? ((max - min) / avg) * 100 : 0;
  return {
    available: true,
    label,
    detail,
    imbalance,
    color: imbalance > 25 ? "#ef4444" : imbalance > 12 ? "#f59e0b" : "#22c55e",
  };
}

function formatWatts(value) {
  if (!Number.isFinite(value) || value <= 0) return "--";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} kW` : `${value.toFixed(0)} W`;
}

function healthColor(health) {
  if (health === "alarm") return "#ef4444";
  if (health === "attention") return "#f59e0b";
  return "#22c55e";
}

function healthGlow(health) {
  if (health === "alarm") return "rgba(239,68,68,.65)";
  if (health === "attention") return "rgba(245,158,11,.65)";
  return "rgba(34,197,94,.55)";
}

function tile(label, value, detail, color) {
  return `
    <div class="tile">
      <span><i class="dot" style="--dot:${color}"></i>${escapeHtml(label)}</span>
      <b>${escapeHtml(value)}</b>
      <small>${escapeHtml(detail)}</small>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

if (!customElements.get("ldcs-rack-status-card")) {
  customElements.define("ldcs-rack-status-card", LdcsRackStatusCard);
}
