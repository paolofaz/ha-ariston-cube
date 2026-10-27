/* Ariston Cube weekly Lovelace view. Read-only; no cloud write or polling. */
(function () {
  "use strict";
  const DAYS = [
    ["Lunedì", "Lun"], ["Martedì", "Mar"], ["Mercoledì", "Mer"],
    ["Giovedì", "Gio"], ["Venerdì", "Ven"], ["Sabato", "Sab"],
    ["Domenica", "Dom"]
  ];
  const css = [
    ":host{display:block;color:var(--primary-text-color)}",
    "ha-card{display:block;padding:20px 18px}",
    "h2{font-size:1.12rem;font-weight:600;margin:0 0 4px}",
    ".subtitle,.footer,.times{color:var(--secondary-text-color);font-size:.75rem}",
    ".subtitle{margin:0 0 14px}.footer{margin:16px 0 0}",
    ".axis{margin:4px 0 8px 49px;display:flex;justify-content:space-between;font-size:.73rem;color:var(--secondary-text-color)}",
    ".day{display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;column-gap:11px;padding:9px 0;border-top:1px solid var(--divider-color)}",
    ".day.today .name{font-weight:700;color:var(--primary-color)}",
    ".name{font-size:.82rem;font-weight:600}",
    ".bar{height:32px;position:relative;overflow:hidden;border:1px solid var(--divider-color);border-radius:7px;background:var(--secondary-background-color)}",
    ".segment{position:absolute;top:0;bottom:0}",
    ".segment.comfort{background:var(--primary-color,#5b9ad0)}",
    ".segment.economy{background:color-mix(in srgb,var(--primary-color,#5b9ad0) 27%,var(--card-background-color,#fff))}",
    ".segment.unknown{background:repeating-linear-gradient(45deg,var(--disabled-text-color) 0px 3px,var(--secondary-background-color) 3px 6px)}",
    ".times{grid-column:2;margin:4px 0 0;line-height:1.35}",
    ".legend{display:flex;gap:19px;align-items:center;margin-top:14px;font-size:.8rem}",
    ".dot{width:12px;height:12px;border-radius:3px;display:inline-block;margin-right:6px}",
    ".dot.comfort{background:var(--primary-color,#5b9ad0)}",
    ".dot.economy{background:color-mix(in srgb,var(--primary-color,#5b9ad0) 27%,var(--card-background-color,#fff))}",
    "@media(min-width:700px){.day{grid-template-columns:38px minmax(0,1fr) minmax(190px,1fr)}.times{grid-column:3;margin-left:12px}.bar{height:34px}}"
  ].join("");

  const el = (tag, className, text) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text != null) item.textContent = String(text);
    return item;
  };

  function parseDay(value) {
    if (typeof value !== "string") return null;
    const points = [];
    const pattern = /(?:^|·)\s*(\d{1,2}):(\d{2})\s+(Comfort|Economy)\b/gi;
    for (const hit of value.matchAll(pattern)) {
      const h = Number(hit[1]), m = Number(hit[2]);
      if (h < 24 && m < 60) points.push({
        minute: h * 60 + m,
        preset: hit[3].toLowerCase()
      });
    }
    points.sort((a, b) => a.minute - b.minute);
    return points.length ? points : null;
  }

  function intervals(weekly, dayIndex) {
    if (!weekly[dayIndex]) return null;
    const pieces = [...weekly[dayIndex]];
    if (pieces[0].minute > 0) {
      const prev = weekly[(dayIndex + 6) % 7];
      pieces.unshift({
        minute: 0, preset: prev && prev.length
          ? prev[prev.length - 1].preset : "unknown"
      });
    }
    return pieces.map((point, i) => ({
      start: point.minute,
      end: i + 1 < pieces.length ? pieces[i + 1].minute : 1440,
      preset: point.preset
    })).filter((period) => period.end > period.start);
  }

  class AristonCubeWeeklyCard extends HTMLElement {
    static getStubConfig() {
      return {entity: "sensor.replace_with_weekly_program_sensor"};
    }
    setConfig(config) {
      if (!config || typeof config.entity !== "string" || !config.entity.startsWith("sensor.")) {
        throw new Error("Indica l'entità del sensore Programma settimanale Cube S.");
      }
      this.config = {entity: config.entity, title: config.title || "Fasce riscaldamento Cube S"};
      if (!this.shadowRoot) this.attachShadow({mode: "open"});
      this.key = "";
      if (this.homeAssistant) this.render();
    }
    set hass(value) {
      this.homeAssistant = value;
      if (this.config) this.render();
    }
    getCardSize() {return 6;}
    render() {
      const state = this.homeAssistant.states[this.config.entity];
      const values = DAYS.map((d) => state && state.attributes[d[0]]);
      const current = JSON.stringify([state && state.state, values, this.config.title]);
      if (this.key === current) return;
      this.key = current;
      const weekly = values.map(parseDay);
      const activeDay = (new Date().getDay() + 6) % 7;
      const root = this.shadowRoot;
      const style = el("style"); style.textContent = css;
      const haCard = el("ha-card");
      haCard.append(el("h2", "", this.config.title));
      haCard.append(el("p", "subtitle", "Programmazione reale del Cube S"));
      if (!state) haCard.append(el("p", "subtitle", "Sensore non disponibile: " + this.config.entity));
      const axis = el("div", "axis");
      for (const hour of ["00", "06", "12", "18", "24"]) {
        axis.append(el("span", "", hour));
      }
      haCard.append(axis);
      DAYS.forEach(([name, short], index) => {
        const row = el("div", "day" + (index === activeDay ? " today" : ""));
        row.append(el("span", "name", short));
        const bar = el("div", "bar");
        const slices = intervals(weekly, index);
        if (slices) slices.forEach((period) => {
          const segment = el("span", "segment " + period.preset);
          segment.style.left = (period.start / 1440 * 100) + "%";
          segment.style.width = ((period.end - period.start) / 1440 * 100) + "%";
          const t = (m) => String(Math.floor(m / 60)).padStart(2, "0")
            + ":" + String(m % 60).padStart(2, "0");
          segment.title = t(period.start) + "–" + t(period.end) + " " + period.preset;
          bar.append(segment);
        });
        row.append(bar);
        row.append(el("p", "times", values[index] || "Nessun programma disponibile"));
        haCard.append(row);
      });
      const legend = el("div", "legend");
      for (const preset of ["comfort", "economy"]) {
        const item = el("span");
        item.append(el("i", "dot " + preset));
        item.append(document.createTextNode(preset === "comfort" ? "Comfort" : "Economy"));
        legend.append(item);
      }
      haCard.append(legend);
      haCard.append(el("p", "footer", "Sola lettura: le fasce originali restano gestite dal Cube S."));
      root.replaceChildren(style, haCard);
    }
  }
  if (!customElements.get("ariston-cube-weekly-card")) {
    customElements.define("ariston-cube-weekly-card", AristonCubeWeeklyCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "ariston-cube-weekly-card",
      name: "Ariston Cube · Settimana Comfort/Economy",
      description: "Timeline settimanale dalla programmazione originale Cube S"
    });
  }
})();
