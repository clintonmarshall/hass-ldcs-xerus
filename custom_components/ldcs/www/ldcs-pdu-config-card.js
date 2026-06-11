class LdcsPduConfigCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 8;
  }

  render() {
    if (!this._hass || !this.config) return;
    const entities = this.config.entities || [];
    const snapshots = entities
      .map((entityId) => ({ entityId, stateObj: this._hass.states[entityId] }))
      .filter((item) => item.stateObj)
      .map((item) => ({ entityId: item.entityId, state: item.stateObj.state, attrs: item.stateObj.attributes || {} }));

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          .wrap { padding:18px; }
          .top { display:flex; justify-content:space-between; gap:14px; align-items:flex-start; margin-bottom:16px; }
          .title { font-size:20px; font-weight:760; line-height:1.15; }
          .sub { color:var(--secondary-text-color); font-size:13px; margin-top:5px; }
          .summary { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; margin-bottom:16px; }
          .metric { border:1px solid rgba(148,163,184,.22); border-radius:8px; padding:12px; background:rgba(255,255,255,.04); }
          .metric span { display:block; color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; font-weight:800; }
          .metric b { display:block; margin-top:5px; font-size:22px; }
          .pdu { border:1px solid rgba(148,163,184,.24); border-radius:8px; margin-top:14px; overflow:hidden; }
          .pduHead { display:flex; justify-content:space-between; gap:12px; padding:14px; background:rgba(15,23,42,.06); border-bottom:1px solid rgba(148,163,184,.18); }
          .pduName { font-size:16px; font-weight:760; }
          .pduState { color:var(--secondary-text-color); font-size:12px; margin-top:4px; }
          .topology { font-size:12px; color:var(--secondary-text-color); text-align:right; }
          .body { padding:14px; display:grid; gap:16px; }
          .chips { display:flex; flex-wrap:wrap; gap:8px; }
          .chip { display:inline-flex; align-items:center; gap:7px; border:1px solid rgba(148,163,184,.22); border-radius:999px; padding:7px 10px; font-size:12px; background:rgba(255,255,255,.035); }
          .dot { width:8px; height:8px; border-radius:999px; background:var(--dot); box-shadow:0 0 10px var(--dot); }
          .grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
          .block { min-width:0; }
          .blockTitle { display:flex; align-items:center; gap:8px; font-weight:740; margin-bottom:8px; }
          .feed { border:1px solid rgba(14,165,233,.25); border-radius:8px; padding:12px; background:rgba(14,165,233,.055); }
          .feedGrid { display:grid; grid-template-columns:repeat(4, minmax(0, 1fr)); gap:10px; margin-top:10px; }
          .feedItem span { display:block; color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; font-weight:800; }
          .feedItem b { display:block; font-size:13px; margin-top:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          table { width:100%; border-collapse:collapse; font-size:12px; table-layout:fixed; }
          th { text-align:left; color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; padding:7px 6px; border-bottom:1px solid rgba(148,163,184,.22); }
          td { padding:8px 6px; border-bottom:1px solid rgba(148,163,184,.12); vertical-align:top; overflow:hidden; text-overflow:ellipsis; }
          .muted { color:var(--secondary-text-color); }
          .enabled { color:#16a34a; font-weight:760; }
          .disabled { color:#64748b; font-weight:760; }
          .warn { color:#d97706; font-weight:760; }
          .empty { color:var(--secondary-text-color); font-size:12px; padding:10px; border:1px dashed rgba(148,163,184,.25); border-radius:8px; }
          @media (max-width: 1050px) { .summary, .grid, .feedGrid { grid-template-columns:1fr; } .topology { text-align:left; } .pduHead { flex-direction:column; } }
        </style>
        <div class="wrap">
          <div class="top">
            <div>
              <div class="title">${escapeHtml(this.config.title || "PDU Configuration Snapshot")}</div>
              <div class="sub">Services, data push destinations, event rules, actions, door access rules, and link topology</div>
            </div>
          </div>
          ${summaryTemplate(snapshots)}
          ${snapshots.length ? snapshots.map(snapshotTemplate).join("") : `<div class="empty">No PDU config snapshot entities found for this rack yet.</div>`}
        </div>
      </ha-card>
    `;
  }
}

function summaryTemplate(snapshots) {
  const totals = snapshots.reduce((acc, item) => {
    const counts = item.attrs.configuration_counts || {};
    acc.services += Number(counts.enabled_service_count || 0);
    acc.rules += Number(counts.event_rule_count || 0);
    acc.datapush += Number(counts.datapush_entry_count || 0);
    acc.doorRules += Number(counts.door_access_rule_count || 0);
    return acc;
  }, { services: 0, rules: 0, datapush: 0, doorRules: 0 });
  return `
    <div class="summary">
      ${metricTemplate("PDUs", snapshots.length)}
      ${metricTemplate("Enabled Services", totals.services)}
      ${metricTemplate("Event Rules", totals.rules)}
      ${metricTemplate("Data Push", totals.datapush)}
    </div>
  `;
}

function metricTemplate(label, value) {
  return `<div class="metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b></div>`;
}

function snapshotTemplate(snapshot) {
  const attrs = snapshot.attrs;
  const counts = attrs.configuration_counts || {};
  const topology = attrs.topology || {};
  const primary = topology.primary || {};
  const services = attrs.services || {};
  const datapush = attrs.data_push_entries || [];
  const managedMqtt = attrs.managed_mqtt_datapush || {};
  const mqttEvents = attrs.recent_mqtt_events || [];
  const actionTypes = attrs.event_action_types || [];
  const actions = attrs.event_actions || [];
  const rules = attrs.event_rules || [];
  const doorRules = attrs.door_access_rules || [];
  return `
    <div class="pdu">
      <div class="pduHead">
        <div>
          <div class="pduName">${escapeHtml(primary.name || attrs.friendly_name || snapshot.entityId)}</div>
          <div class="pduState">${escapeHtml(snapshot.state)} · ${escapeHtml(primary.model || "")} ${escapeHtml(primary.serial_number || "")}</div>
        </div>
        <div class="topology">
          ${escapeHtml(topology.mode || "unknown topology")}<br>
          ${escapeHtml(Number(counts.linked_pdu_count || 0))} linked PDU(s)
        </div>
      </div>
      <div class="body">
        <div class="block">
          <div class="blockTitle">Services</div>
          <div class="chips">${Object.entries(services).map(([name, service]) => serviceChip(name, service)).join("")}</div>
        </div>
        ${mqttFeedTemplate(managedMqtt, mqttEvents)}
        <div class="grid">
          ${tableBlock("Data Push", ["ID", "Type", "Destination", "Topic"], datapush.map((entry) => [
            entry.id,
            entry.type,
            entry.url || "-",
            entry.mqtt_topic_prefix || "-",
          ]))}
          ${tableBlock("Event Rules", ["Rule", "Enabled", "Actions"], rules.map((rule) => [
            rule.name || rule.id,
            rule.enabled ? "yes" : "no",
            (rule.actions || []).map((action) => action.name || action.id).filter(Boolean).join(", ") || "-",
          ]))}
          ${tableBlock("Event Actions", ["Action", "Type", "System"], actions.map((action) => [
            action.name || action.id,
            action.type || "-",
            action.is_system ? "yes" : "no",
          ]))}
          ${tableBlock("Event Action Types", ["Type"], actionTypes.map((type) => [type]))}
          ${tableBlock("Door Rules", ["Rule", "Handles", "Timeout"], doorRules.map((rule) => [
            rule.name || rule.id,
            Array.isArray(rule.door_handle_locks) ? rule.door_handle_locks.length : "-",
            rule.conditions_timeout || "-",
          ]))}
        </div>
      </div>
    </div>
  `;
}

function mqttFeedTemplate(managedMqtt, mqttEvents) {
  const lastEvent = mqttEvents[0] || {};
  const status = managedMqtt.configured === true ? "configured" : managedMqtt.enabled ? "pending" : "disabled";
  const errors = managedMqtt.errors || [];
  return `
    <div class="feed">
      <div class="blockTitle">Managed MQTT Event Feed</div>
      <div class="feedGrid">
        <div class="feedItem"><span>Status</span><b>${escapeHtml(status)}</b></div>
        <div class="feedItem"><span>Broker</span><b>${escapeHtml(managedMqtt.broker || "-")}</b></div>
        <div class="feedItem"><span>Topic Prefix</span><b>${escapeHtml(managedMqtt.topic_prefix || "-")}</b></div>
        <div class="feedItem"><span>Messages</span><b>${escapeHtml(managedMqtt.message_count || mqttEvents.length || 0)}</b></div>
        <div class="feedItem"><span>Last Topic</span><b>${escapeHtml(managedMqtt.last_topic || lastEvent.topic || "-")}</b></div>
        <div class="feedItem"><span>Last Seen</span><b>${escapeHtml(managedMqtt.last_message_time || lastEvent.timestamp || "-")}</b></div>
        <div class="feedItem"><span>Created</span><b>${escapeHtml((managedMqtt.created_entry_ids || []).join(", ") || "-")}</b></div>
        <div class="feedItem"><span>Errors</span><b>${escapeHtml(errors.length ? errors.join("; ") : "-")}</b></div>
      </div>
    </div>
  `;
}

function serviceChip(name, service) {
  const configured = service?.configured;
  const reachable = service?.reachable;
  let state = "unknown";
  let color = "#64748b";
  if (configured === false) {
    state = "disabled";
  } else if (reachable === true) {
    state = "online";
    color = "#16a34a";
  } else if (configured === true) {
    state = reachable === false ? "blocked" : "enabled";
    color = reachable === false ? "#dc2626" : "#d97706";
  }
  const detail = [service?.port ? `:${service.port}` : "", service?.readonly ? "RO" : ""].filter(Boolean).join(" ");
  return `<span class="chip" title="${escapeHtml(JSON.stringify(service || {}))}" style="--dot:${color}"><span class="dot"></span>${escapeHtml(labelize(name))} <span class="muted">${escapeHtml(state)} ${escapeHtml(detail)}</span></span>`;
}

function tableBlock(title, headers, rows) {
  if (!rows.length) return `<div class="block"><div class="blockTitle">${escapeHtml(title)}</div><div class="empty">No configured ${escapeHtml(title.toLowerCase())} found.</div></div>`;
  return `
    <div class="block">
      <div class="blockTitle">${escapeHtml(title)}</div>
      <table>
        <thead><tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr></thead>
        <tbody>${rows.slice(0, 24).map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell ?? "")}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

function labelize(value) {
  return String(value).replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
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

if (!customElements.get("ldcs-pdu-config-card")) {
  customElements.define("ldcs-pdu-config-card", LdcsPduConfigCard);
}
