class RaritanCoolingCard extends HTMLElement {
  setConfig(config) {
    this.config = config;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    this._hass = hass;
    this.render();
  }

  getCardSize() {
    return 5;
  }

  render() {
    if (!this._hass || !this.config) return;
    const e = this.config.entities || {};
    const state = (id) => (id && this._hass.states[id] ? this._hass.states[id].state : "unknown");
    const num = (id) => {
      const value = Number.parseFloat(state(id));
      return Number.isFinite(value) ? value : null;
    };
    const temp = (id) => {
      const value = num(id);
      return value === null ? "--" : `${value.toFixed(1)} C`;
    };
    const pct = (id) => {
      const value = num(id);
      return value === null ? "--" : `${Math.round(value)}%`;
    };
    const fan = num(e.fanFeedback) ?? num(e.fanCommand) ?? 0;
    const valve = num(e.valveFeedback) ?? num(e.valveRequest) ?? 0;
    const supply = num(e.airOff) ?? num(e.altAirOff);
    const ret = num(e.airOn) ?? num(e.altAirOn);
    const room = num(e.roomTemp);
    const frontA = num(e.rackFrontA);
    const frontB = num(e.rackFrontB);
    const hotA = num(e.rackRearA);
    const hotB = num(e.rackRearB);
    const rackFront = [frontA, frontB].filter(Number.isFinite);
    const rackRear = [hotA, hotB].filter(Number.isFinite);
    const avgFront = rackFront.length ? rackFront.reduce((a, b) => a + b, 0) / rackFront.length : null;
    const avgRear = rackRear.length ? rackRear.reduce((a, b) => a + b, 0) / rackRear.length : null;
    const delta = supply !== null && ret !== null ? ret - supply : null;
    const fanDuration = Math.max(0.45, 3.5 - Math.min(Math.max(fan, 0), 100) / 35);
    const valveOpen = Math.min(Math.max(valve, 0), 100);
    const alarm = state(e.globalAlarm) === "on" || state(e.leakAlarm) === "on";
    const warning = [
      e.coilWarning,
      e.filterWarning,
      e.fanWarning,
      e.serviceWarning,
      e.valveWarning,
    ].some((id) => state(id) === "on");
    const health = alarm ? "alarm" : warning ? "warning" : state(e.unitOn) === "on" ? "cooling" : "standby";
    const healthColor = alarm ? "#ef4444" : warning ? "#f59e0b" : state(e.unitOn) === "on" ? "#22c55e" : "#94a3b8";

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          :host {
            --cool: #38bdf8;
            --cold: #0ea5e9;
            --hot: #ef4444;
            --warm: #f97316;
            --ink: var(--primary-text-color);
            --muted: var(--secondary-text-color);
          }
          .wrap {
            padding: 18px;
            color: var(--ink);
            background:
              radial-gradient(circle at 12% 18%, rgba(56,189,248,.18), transparent 28%),
              radial-gradient(circle at 84% 18%, rgba(239,68,68,.16), transparent 28%),
              linear-gradient(135deg, rgba(15,23,42,.04), rgba(14,165,233,.05));
            border-radius: 12px;
            overflow: hidden;
          }
          .top {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: start;
            margin-bottom: 16px;
          }
          .title {
            font-size: 20px;
            font-weight: 650;
            line-height: 1.15;
          }
          .sub {
            color: var(--muted);
            margin-top: 4px;
            font-size: 13px;
          }
          .status {
            border: 1px solid color-mix(in srgb, ${healthColor} 48%, transparent);
            background: color-mix(in srgb, ${healthColor} 14%, transparent);
            color: ${healthColor};
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            white-space: nowrap;
          }
          .scene {
            display: grid;
            grid-template-columns: 1fr 1.05fr 1fr;
            gap: 14px;
            min-height: 260px;
            align-items: stretch;
          }
          .zone {
            position: relative;
            border: 1px solid rgba(148,163,184,.28);
            border-radius: 10px;
            background: rgba(15,23,42,.04);
            overflow: hidden;
            min-height: 250px;
          }
          .label {
            position: absolute;
            top: 10px;
            left: 12px;
            z-index: 2;
            font-size: 12px;
            font-weight: 700;
            color: var(--muted);
            text-transform: uppercase;
          }
          .cold {
            background: linear-gradient(180deg, rgba(14,165,233,.22), rgba(56,189,248,.06));
          }
          .hot {
            background: linear-gradient(180deg, rgba(239,68,68,.22), rgba(249,115,22,.08));
          }
          .rack {
            display: grid;
            grid-template-rows: repeat(8, 1fr);
            gap: 6px;
            padding: 42px 24px 20px;
            background: linear-gradient(180deg, rgba(2,6,23,.85), rgba(30,41,59,.92));
          }
          .server {
            border: 1px solid rgba(148,163,184,.38);
            border-radius: 5px;
            background: linear-gradient(90deg, rgba(15,23,42,.9), rgba(51,65,85,.92));
            position: relative;
          }
          .server:before {
            content: "";
            position: absolute;
            left: 8px;
            top: 50%;
            width: 7px;
            height: 7px;
            transform: translateY(-50%);
            border-radius: 999px;
            background: ${healthColor};
            box-shadow: 0 0 10px ${healthColor};
          }
          .arrows {
            position: absolute;
            inset: 42px 8px 18px;
          }
          .arrow {
            position: absolute;
            width: 58%;
            height: 8px;
            border-radius: 999px;
            opacity: .78;
            animation: flow 1.7s linear infinite;
          }
          .cold .arrow {
            left: -58%;
            background: linear-gradient(90deg, transparent, var(--cool));
          }
          .hot .arrow {
            right: -58%;
            background: linear-gradient(270deg, transparent, var(--hot));
            animation-name: flowBack;
          }
          .arrow:nth-child(1) { top: 18%; animation-delay: 0s; }
          .arrow:nth-child(2) { top: 39%; animation-delay: .35s; }
          .arrow:nth-child(3) { top: 60%; animation-delay: .7s; }
          .arrow:nth-child(4) { top: 81%; animation-delay: 1.05s; }
          @keyframes flow { from { transform: translateX(0); } to { transform: translateX(190%); } }
          @keyframes flowBack { from { transform: translateX(0); } to { transform: translateX(-190%); } }
          .rdhx {
            position: absolute;
            right: 12px;
            top: 48px;
            bottom: 20px;
            width: 44px;
            border-radius: 8px;
            background: linear-gradient(180deg, rgba(30,41,59,.9), rgba(15,23,42,.95));
            border: 1px solid rgba(148,163,184,.38);
            display: grid;
            place-items: center;
          }
          .fan {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            background:
              conic-gradient(from 0deg, var(--cool), transparent 22%, var(--cool) 34%, transparent 54%, var(--cool) 68%, transparent 84%);
            animation: spin ${fanDuration}s linear infinite;
            opacity: ${state(e.unitOn) === "on" ? "1" : ".35"};
          }
          @keyframes spin { to { transform: rotate(360deg); } }
          .metrics {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px;
            margin-top: 14px;
          }
          .metric {
            border: 1px solid rgba(148,163,184,.24);
            border-radius: 8px;
            padding: 10px;
            background: rgba(255,255,255,.04);
          }
          .metric .name {
            color: var(--muted);
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
          }
          .metric .value {
            margin-top: 5px;
            font-size: 18px;
            font-weight: 700;
          }
          .valve {
            height: 8px;
            background: rgba(148,163,184,.25);
            border-radius: 999px;
            overflow: hidden;
            margin-top: 7px;
          }
          .valve > span {
            display: block;
            height: 100%;
            width: ${valveOpen}%;
            background: linear-gradient(90deg, var(--cool), #22c55e);
            transition: width .45s ease;
          }
          @media (max-width: 760px) {
            .scene { grid-template-columns: 1fr; }
            .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
          }
        </style>
        <div class="wrap">
          <div class="top">
            <div>
              <div class="title">${this.config.title || "Rack Cooling"}</div>
              <div class="sub">Cold aisle, rack heat load, RDHx removal path</div>
            </div>
            <div class="status">${health}</div>
          </div>
          <div class="scene">
            <div class="zone cold">
              <div class="label">Supply air</div>
              <div class="arrows"><i class="arrow"></i><i class="arrow"></i><i class="arrow"></i><i class="arrow"></i></div>
              <div class="metric" style="position:absolute;left:12px;bottom:14px;right:12px">
                <div class="name">RDHx air off</div><div class="value">${temp(e.airOff)}</div>
              </div>
            </div>
            <div class="zone rack">
              <div class="label">Rack 02 IT load</div>
              ${Array.from({ length: 8 }, () => '<div class="server"></div>').join("")}
            </div>
            <div class="zone hot">
              <div class="label">Return air</div>
              <div class="arrows"><i class="arrow"></i><i class="arrow"></i><i class="arrow"></i><i class="arrow"></i></div>
              <div class="rdhx"><div class="fan"></div></div>
              <div class="metric" style="position:absolute;left:12px;bottom:14px;right:68px">
                <div class="name">RDHx air on</div><div class="value">${temp(e.airOn)}</div>
              </div>
            </div>
          </div>
          <div class="metrics">
            <div class="metric"><div class="name">Rack front avg</div><div class="value">${avgFront === null ? "--" : `${avgFront.toFixed(1)} C`}</div></div>
            <div class="metric"><div class="name">Rack rear avg</div><div class="value">${avgRear === null ? "--" : `${avgRear.toFixed(1)} C`}</div></div>
            <div class="metric"><div class="name">Cooling delta T</div><div class="value">${delta === null ? "--" : `${delta.toFixed(1)} C`}</div></div>
            <div class="metric"><div class="name">Room temp</div><div class="value">${room === null ? "--" : `${room.toFixed(1)} C`}</div></div>
            <div class="metric"><div class="name">Fan feedback</div><div class="value">${pct(e.fanFeedback)}</div></div>
            <div class="metric"><div class="name">Fan command</div><div class="value">${pct(e.fanCommand)}</div></div>
            <div class="metric"><div class="name">Valve feedback</div><div class="value">${pct(e.valveFeedback)}<div class="valve"><span></span></div></div></div>
            <div class="metric"><div class="name">Valve request</div><div class="value">${pct(e.valveRequest)}</div></div>
          </div>
        </div>
      </ha-card>
    `;
  }
}

if (!customElements.get("raritan-cooling-card")) {
  customElements.define("raritan-cooling-card", RaritanCoolingCard);
}
