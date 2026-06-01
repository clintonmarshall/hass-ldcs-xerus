class RaritanWaveformCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) throw new Error("raritan-waveform-card requires an entity");
    this.config = config;
    this.innerHTML = `
      <ha-card>
        <div class="header"></div>
        <div class="meta"></div>
        <canvas></canvas>
        <div class="legend">
          <span><i class="voltage"></i> Voltage</span>
          <span><i class="current"></i> Current</span>
        </div>
      </ha-card>`;
    this.style.display = "block";
    this.querySelector("ha-card").style.cssText = "padding:16px;";
    this.querySelector(".header").style.cssText = "font-size:16px;font-weight:500;margin-bottom:4px;";
    this.querySelector(".meta").style.cssText = "font-size:12px;color:var(--secondary-text-color);margin-bottom:10px;";
    this.querySelector("canvas").style.cssText = "display:block;width:100%;height:220px;";
    this.querySelector(".legend").style.cssText = "display:flex;gap:16px;font-size:12px;color:var(--secondary-text-color);margin-top:8px;";
    for (const item of this.querySelectorAll("i")) {
      item.style.cssText = "display:inline-block;width:18px;height:3px;margin:0 5px 3px 0;";
    }
    this.querySelector(".voltage").style.background = "#dc3f45";
    this.querySelector(".current").style.background = "#1f8f78";
  }

  set hass(hass) {
    if (!this.config) return;
    const state = hass.states[this.config.entity];
    const attrs = state ? state.attributes : {};
    const voltage = attrs.voltage_samples || [];
    const current = attrs.current_samples || [];
    const rate = attrs.sample_rate_hz || 0;
    this.querySelector(".header").textContent = this.config.name || state?.attributes.friendly_name || "PX4 waveform";
    this.querySelector(".meta").textContent =
      voltage.length || current.length
        ? `${Math.max(voltage.length, current.length)} samples at ${rate} Hz`
        : "No waveform capture available";
    this.draw(voltage, current);
  }

  draw(voltage, current) {
    const canvas = this.querySelector("canvas");
    const width = Math.max(canvas.clientWidth, 320);
    const height = 220;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    const ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = getComputedStyle(this).getPropertyValue("--divider-color") || "#c8c8c8";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
    this.line(ctx, voltage, width, height, "#dc3f45");
    this.line(ctx, current, width, height, "#1f8f78");
  }

  line(ctx, samples, width, height, color) {
    if (!samples.length) return;
    const max = Math.max(...samples.map((value) => Math.abs(value)), 0.001);
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    samples.forEach((value, index) => {
      const x = (index / Math.max(samples.length - 1, 1)) * width;
      const y = height / 2 - (value / max) * (height * 0.43);
      if (index === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  getCardSize() {
    return 4;
  }
}

customElements.define("raritan-waveform-card", RaritanWaveformCard);
