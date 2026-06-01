class RaritanOutletLoadCard extends HTMLElement {
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
    const entities = this.config.entities || [];
    const rows = entities.map((entity, index) => this.row(entity, index + 1)).join("");
    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          .wrap { padding:16px; }
          .title { font-size:20px; font-weight:700; margin-bottom:4px; }
          .sub { color:var(--secondary-text-color); font-size:13px; margin-bottom:14px; }
          .grid { display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap:8px; }
          .outlet { border:1px solid rgba(148,163,184,.24); border-radius:8px; padding:9px; background:rgba(255,255,255,.04); min-width:0; }
          .head { display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:8px; }
          .name { font-weight:700; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
          .now { font-size:16px; font-weight:800; }
          .bar { height:8px; border-radius:999px; background:rgba(148,163,184,.22); overflow:hidden; margin:8px 0; }
          .bar span { display:block; height:100%; width:var(--w); background:linear-gradient(90deg,#22c55e,#f59e0b,#ef4444); transition:width .4s ease; }
          .meta { display:grid; grid-template-columns:1fr 1fr; gap:5px; color:var(--secondary-text-color); font-size:11px; }
          .meta b { color:var(--primary-text-color); font-size:12px; }
          @media (max-width: 760px) { .grid { grid-template-columns:1fr; } }
        </style>
        <div class="wrap">
          <div class="title">${this.config.title || "Outlet Load History"}</div>
          <div class="sub">Current load with PDU-maintained minimum and maximum readings</div>
          <div class="grid">${rows}</div>
        </div>
      </ha-card>
    `;
  }

  row(entity, number) {
    const stateObj = this._hass.states[entity] || {};
    const attrs = stateObj.attributes || {};
    const now = Number.parseFloat(stateObj.state);
    const min = Number.parseFloat(attrs.minimum_reading);
    const max = Number.parseFloat(attrs.maximum_reading);
    const maxForBar = Number.isFinite(max) && max > 0 ? max : Math.max(now || 0, 1);
    const width = Number.isFinite(now) ? Math.max(2, Math.min(100, now / maxForBar * 100)) : 0;
    const name = attrs.configured_name || attrs.friendly_name || `Outlet ${number}`;
    const unit = attrs.unit_of_measurement || "W";
    return `
      <div class="outlet">
        <div class="head"><div class="name">${escapeHtml(name)}</div><div class="now">${fmt(now)} ${unit}</div></div>
        <div class="bar" style="--w:${width}%"><span></span></div>
        <div class="meta">
          <div>Minimum<br><b>${fmt(min)} ${unit}</b></div>
          <div>Maximum<br><b>${fmt(max)} ${unit}</b></div>
          <div>First/min time<br><b>${shortTime(attrs.minimum_reading_timestamp || attrs.extrema_observed_since)}</b></div>
          <div>Last/max time<br><b>${shortTime(attrs.maximum_reading_timestamp)}</b></div>
        </div>
      </div>
    `;
  }
}

function fmt(value) {
  return Number.isFinite(value) ? value.toFixed(value >= 10 ? 1 : 2) : "--";
}

function shortTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
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

customElements.define("raritan-outlet-load-card", RaritanOutletLoadCard);
