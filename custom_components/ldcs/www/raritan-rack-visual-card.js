class RaritanRackVisualCard extends HTMLElement {
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
    const state = (id) => (id && this._hass.states[id] ? this._hass.states[id].state : "unknown");
    const attrs = (id) => (id && this._hass.states[id] ? this._hass.states[id].attributes || {} : {});
    const frontDoor = doorState(state(e.frontDoor));
    const rearDoor = doorState(state(e.rearDoor));
    const frontLock = lockState(state(e.frontLock));
    const rearLock = lockState(state(e.rearLock));
    const doorStates = [frontDoor.label, rearDoor.label].filter(Boolean);
    const open = frontDoor.open || rearDoor.open;
    const unlocked = frontLock.unlocked || rearLock.unlocked;
    const alarmA = state(e.alarmA);
    const alarmB = state(e.alarmB);
    const alarm = ["critical", "warning"].includes(alarmA) || ["critical", "warning"].includes(alarmB);
    const critical = alarmA === "critical" || alarmB === "critical";
    const assetInventoryIds = e.assetInventories || [e.assetInventory, e.assetInventoryB].filter(Boolean);
    const assetInventories = assetInventoryIds.map((id) => attrs(id));
    const tags = assetInventories.flatMap((assetAttrs, stripIndex) =>
      (assetAttrs.asset_tags || []).map((tag) => ({ ...tag, stripIndex: stripIndex + 1 }))
    );
    const rackUnits = assetInventories.flatMap((assetAttrs, stripIndex) =>
      (assetAttrs.asset_rack_units || []).map((unit) => ({ ...unit, stripIndex: stripIndex + 1 }))
    );
    const recentAssetRecords = assetInventories.flatMap((assetAttrs) => assetAttrs.asset_log_recent_records || []);
    const ruCount = Number(assetInventories.find((assetAttrs) => assetAttrs.rack_unit_count)?.rack_unit_count) || 42;
    const tagByRu = new Map(tags.map((tag) => [Number(tag.ru || tag.rack_unit_number + 1), tag]));
    const rows = [];
    for (let ru = ruCount; ru >= 1; ru -= 1) {
      const tag = tagByRu.get(ru);
      const rackUnit = rackUnits.find((unit) => Number(unit.ru || unit.rack_unit_number + 1) === ru);
      const occupied = tag || (rackUnit && Number(rackUnit.size) > 0);
      const tagLabel = tag ? tag.raw_id || tag.tag_id || tag.name || `TAG-${ru}` : "";
      rows.push(`
        <div class="ru ${occupied ? "occupied" : ""}" title="${tag ? `RU ${ru}: ${tagLabel}` : `RU ${ru}`}">
          <span>${ru}</span>
          <b>${tag ? escapeHtml(tagLabel) : ""}</b>
        </div>
      `);
    }
    const recentEvents = attrs(e.securityStatus).recent_access_events || [];
    const lastEvent = recentEvents[0];
    const lastAsset = recentAssetRecords[0];
    const outletStates = (e.outletStates || []).map(state);
    const ocpStates = (e.ocpStates || []).map(state);
    const rackPower = (e.rackPower || []).reduce((total, id) => {
      const value = Number.parseFloat(state(id));
      return total + (Number.isFinite(value) ? value : 0);
    }, 0);
    const ocpTripped = ocpStates.some((value) => String(value).toLowerCase().includes("trip"));
    const outletsOn = outletStates.filter((value) => String(value).toLowerCase().includes("on")).length;

    this.shadowRoot.innerHTML = `
      <ha-card>
        <style>
          .wrap { padding: 18px; overflow: hidden; }
          .top { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:14px; }
          .title { font-size:20px; font-weight:700; }
          .subtitle { color:var(--secondary-text-color); font-size:13px; margin-top:4px; }
          .scanner { height:12px; border-radius:999px; background:rgba(15,23,42,.72); overflow:hidden; margin-bottom:16px; border:1px solid rgba(148,163,184,.28); position:relative; }
          .scanner:before { content:""; position:absolute; inset:0 auto 0 0; width:30%; border-radius:999px; background:linear-gradient(90deg, transparent, ${alarm ? "#ef4444" : "#22c55e"}, transparent); animation:scan 1.35s linear infinite; }
          @keyframes scan { 0%{ transform:translateX(-100%); } 100%{ transform:translateX(340%); } }
          .stage { display:grid; grid-template-columns: 1fr 1.25fr 1fr; gap:14px; align-items:stretch; }
          .panel {
            border:1px solid rgba(148,163,184,.28);
            border-radius:10px;
            background:rgba(255,255,255,.04);
            min-height:420px;
            position:relative;
            overflow:hidden;
          }
          .rack {
            padding:12px 16px;
            background:linear-gradient(180deg, rgba(15,23,42,.93), rgba(30,41,59,.96));
            border-color:rgba(148,163,184,.38);
          }
          .rackHead { color:#e2e8f0; font-size:12px; font-weight:700; text-transform:uppercase; margin-bottom:8px; display:flex; justify-content:space-between; }
          .ruGrid { display:grid; grid-template-rows: repeat(${ruCount}, minmax(7px, 1fr)); gap:2px; height:380px; }
          .ru { display:grid; grid-template-columns: 28px 1fr; gap:5px; align-items:center; border-radius:3px; background:rgba(51,65,85,.82); border:1px solid rgba(100,116,139,.32); min-height:0; }
          .ru span { color:#94a3b8; font-size:9px; text-align:center; }
          .ru b { color:#dbeafe; font-size:9px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:650; }
          .ru.occupied { background:linear-gradient(90deg, rgba(34,197,94,.58), rgba(14,165,233,.28)); border-color:rgba(34,197,94,.75); box-shadow:0 0 8px rgba(34,197,94,.18); }
          .doorPanel { display:grid; grid-template-rows:1fr 1fr; gap:12px; padding:14px; background:linear-gradient(180deg, rgba(15,23,42,.04), rgba(14,165,233,.06)); }
          .doorCard { border:1px solid rgba(148,163,184,.24); border-radius:10px; padding:12px; position:relative; overflow:hidden; background:linear-gradient(180deg, rgba(15,23,42,.14), rgba(15,23,42,.04)); }
          .doorCard.open { border-color:rgba(245,158,11,.72); background:linear-gradient(180deg, rgba(245,158,11,.16), rgba(15,23,42,.05)); }
          .doorCard.closed { border-color:rgba(34,197,94,.55); background:linear-gradient(180deg, rgba(34,197,94,.10), rgba(15,23,42,.04)); }
          .doorLabel { display:flex; justify-content:space-between; gap:8px; align-items:center; color:var(--primary-text-color); font-size:13px; font-weight:800; text-transform:uppercase; margin-bottom:10px; }
          .doorLabel span:last-child { color:var(--secondary-text-color); font-size:12px; }
          .doorFrame { width:72%; height:112px; margin:0 auto; border:8px solid rgba(71,85,105,.88); border-radius:10px; perspective:700px; position:relative; background:rgba(15,23,42,.08); }
          .door {
            position:absolute; inset:0; transform-origin:left center; border-radius:4px;
            background:linear-gradient(135deg, var(--door-a), var(--door-b));
            border:2px solid rgba(226,232,240,.22);
            transition:transform .5s ease;
            transform:var(--door-transform);
          }
          .handle { position:absolute; right:16px; top:50%; width:12px; height:48px; border-radius:999px; background:var(--lock-c); box-shadow:0 0 16px var(--lock-c); transform:translateY(-50%); }
          .beaconPanel { padding:18px; display:flex; flex-direction:column; justify-content:space-between; }
          .beacon {
            width:124px; height:124px; margin:20px auto; border-radius:999px;
            background:${alarm ? (critical ? "#ef4444" : "#f59e0b") : "#22c55e"};
            box-shadow:0 0 24px ${alarm ? (critical ? "#ef4444" : "#f59e0b") : "#22c55e"};
            animation:${alarm ? "pulse 1s infinite" : "none"};
            position:relative;
          }
          .beacon:after { content:""; position:absolute; inset:24px; border-radius:999px; background:rgba(255,255,255,.28); }
          @keyframes pulse { 0%,100%{opacity:.55; transform:scale(.96)} 50%{opacity:1; transform:scale(1.04)} }
          .events { font-size:12px; color:var(--secondary-text-color); line-height:1.45; display:grid; gap:12px; }
          .events strong { color:var(--primary-text-color); display:block; font-size:14px; margin-bottom:4px; }
          .lights { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:14px; }
          .light { border:1px solid rgba(148,163,184,.22); border-radius:8px; padding:8px; font-size:11px; text-transform:uppercase; font-weight:800; display:flex; align-items:center; gap:7px; }
          .light i { width:10px; height:10px; border-radius:999px; background:var(--c); box-shadow:0 0 12px var(--c); }
          .metrics { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; margin-top:14px; }
          .metric { border:1px solid rgba(148,163,184,.22); border-radius:8px; padding:10px; background:rgba(255,255,255,.04); }
          .metric span { display:block; color:var(--secondary-text-color); font-size:11px; text-transform:uppercase; font-weight:700; }
          .metric b { display:block; margin-top:5px; font-size:18px; }
          @media (max-width: 850px) { .stage { grid-template-columns:1fr; } .panel { min-height:280px; } }
        </style>
        <div class="wrap">
          <div class="top">
            <div><div class="title">${this.config.title || "Rack Security Visual"}</div><div class="subtitle">Door state, active alarms, and ${ruCount}RU asset occupancy</div></div>
          </div>
          <div class="scanner"></div>
          <div class="stage">
            <div class="panel doorPanel">
              ${doorCard("Front Door", frontDoor, frontLock)}
              ${doorCard("Rear Door", rearDoor, rearLock)}
            </div>
            <div class="panel rack">
              <div class="rackHead"><span>Asset strip</span><span>${tags.length}/${ruCount} occupied</span></div>
              <div class="ruGrid">${rows.join("")}</div>
            </div>
            <div class="panel beaconPanel">
              <div>
                <div class="rackHead" style="color:var(--primary-text-color)"><span>Alarm Beacon</span><span>${alarm ? (critical ? "Critical" : "Warning") : "Normal"}</span></div>
                <div class="lights">
                  <div class="light"><i style="--c:${open ? "#f59e0b" : "#22c55e"}"></i>Door</div>
                  <div class="light"><i style="--c:${unlocked ? "#f59e0b" : "#22c55e"}"></i>Lock</div>
                  <div class="light"><i style="--c:${alarm ? "#ef4444" : "#22c55e"}"></i>Alarm</div>
                  <div class="light"><i style="--c:${ocpTripped ? "#ef4444" : "#22c55e"}"></i>OCP</div>
                  <div class="light"><i style="--c:${outletsOn ? "#38bdf8" : "#94a3b8"}"></i>Outlet</div>
                  <div class="light"><i style="--c:${rackPower > 0 ? "#f59e0b" : "#94a3b8"}"></i>Load</div>
                </div>
                <div class="beacon"></div>
              </div>
              <div class="events">
                <div>
                  <strong>Last rack access</strong>
                  ${lastEvent ? `${lastEvent.event || "state changed"}<br>${lastEvent.context || ""}<br>${lastEvent.timestamp || ""}` : "No door/lock transition recorded since integration start."}
                </div>
                <div>
                  <strong>Last asset event</strong>
                  ${lastAsset ? `${lastAsset.type || "asset event"}<br>RU ${lastAsset.ru || "-"} ${lastAsset.tag_id || ""}<br>${lastAsset.timestamp || ""}` : "No asset strip event records available yet."}
                </div>
              </div>
            </div>
          </div>
          <div class="metrics">
            <div class="metric"><span>PDU A alarms</span><b>${alarmA}</b></div>
            <div class="metric"><span>PDU B alarms</span><b>${alarmB}</b></div>
            <div class="metric"><span>Assets detected</span><b>${tags.length}</b></div>
            <div class="metric"><span>Outlets on</span><b>${outletsOn}/${outletStates.length}</b></div>
            <div class="metric"><span>OCP state</span><b>${ocpTripped ? "Trip" : "Normal"}</b></div>
            <div class="metric"><span>Rack power</span><b>${formatWatts(rackPower)}</b></div>
          </div>
        </div>
      </ha-card>
    `;
  }
}

function doorCard(label, door, lock) {
  const stateClass = door.open ? "open" : "closed";
  const doorA = door.open ? "rgba(245,158,11,.96)" : "rgba(51,65,85,.95)";
  const doorB = door.open ? "rgba(180,83,9,.82)" : "rgba(100,116,139,.82)";
  const lockColor = lock.unlocked ? "#f59e0b" : "#22c55e";
  const transform = door.open ? "rotateY(-58deg)" : "rotateY(0deg)";
  return `
    <div class="doorCard ${stateClass}">
      <div class="doorLabel"><span>${escapeHtml(label)}</span><span>${escapeHtml(door.label)} / ${escapeHtml(lock.label)}</span></div>
      <div class="doorFrame">
        <div class="door" style="--door-a:${doorA};--door-b:${doorB};--door-transform:${transform};">
          <div class="handle" style="--lock-c:${lockColor}"></div>
        </div>
      </div>
    </div>
  `;
}

function doorState(value) {
  const raw = String(value ?? "unknown").toLowerCase();
  const open = raw === "0" || raw === "false" || raw.includes("open") || raw.includes("unlock");
  const closed = raw === "1" || raw === "true" || raw.includes("closed") || raw.includes("locked");
  return { open, label: open ? "Open" : closed ? "Closed" : "Unknown" };
}

function lockState(value) {
  const raw = String(value ?? "unknown").toLowerCase();
  const unlocked = raw === "0" || raw === "false" || raw.includes("unlock") || raw.includes("open");
  const locked = raw === "1" || raw === "true" || raw.includes("locked") || raw.includes("closed");
  return { unlocked, label: unlocked ? "Unlocked" : locked ? "Locked" : "Unknown" };
}

function formatWatts(value) {
  if (!Number.isFinite(value) || value <= 0) return "--";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} kW` : `${value.toFixed(0)} W`;
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

if (!customElements.get("raritan-rack-visual-card")) {
  customElements.define("raritan-rack-visual-card", RaritanRackVisualCard);
}
