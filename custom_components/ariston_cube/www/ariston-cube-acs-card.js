/* Ariston Cube ACS panel: one temperature slider and one Comfort button.
 * It only calls supported Home Assistant services after user interaction.
 * No external fetch, session data or timer; no own temperature conversion.
 */
(() => {
  "use strict";

  const css = [
    ":host{display:block}",
    "ha-card{padding:18px 20px;box-sizing:border-box}",
    ".header{display:flex;align-items:center;justify-content:space-between;gap:12px}",
    "h2{font-size:1.1rem;font-weight:500;margin:0}",
    ".value{font-size:1.75rem;font-weight:600;font-variant-numeric:tabular-nums}",
    ".subtitle{color:var(--secondary-text-color);font-size:.85rem;margin:6px 0 16px}",
    "input[type=range]{width:100%;accent-color:var(--primary-color);cursor:pointer}",
    "input[type=range]:disabled{opacity:.35;cursor:not-allowed}",
    ".limits{display:flex;justify-content:space-between;color:var(--secondary-text-color);font-size:.8rem}",
    ".controls{margin-top:18px;padding-top:14px;border-top:1px solid var(--divider-color)}",
    "button{padding:10px 15px;background:var(--secondary-background-color);color:var(--primary-text-color);border-radius:14px;border:1px solid var(--divider-color);font:inherit;cursor:pointer}",
    "button[aria-pressed=true]{background:var(--primary-color);color:var(--text-primary-color,white)}",
    "button:disabled{opacity:.45;cursor:not-allowed}",
    ".error{color:var(--error-color);font-size:.83rem;margin-top:10px}"
  ].join("");

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };

  class AristonCubeAcsCard extends HTMLElement {
    static getStubConfig() {
      return {
        entity: "water_heater.replace_with_real_acs_entity",
        comfort_entity: "switch.replace_with_real_comfort_entity"
      };
    }

    setConfig(config) {
      if (!config || typeof config.entity !== "string" ||
          !config.entity.startsWith("water_heater.") ||
          typeof config.comfort_entity !== "string" ||
          !config.comfort_entity.startsWith("switch.")) {
        throw new Error("Indica un water_heater ACS e lo switch Comfort ACS.");
      }
      this.config = {
        entity: config.entity,
        comfort_entity: config.comfort_entity,
        title: config.title || "Acqua calda sanitaria"
      };
      if (!this.shadowRoot) this.attachShadow({mode: "open"});
      this.render();
    }

    set hass(value) {
      this.homeAssistant = value;
      if (this.config && !this.busy && !this.dragging) this.render();
    }

    getCardSize() { return 3; }

    async commitTemperature(value) {
      if (!this.homeAssistant || !this.config || this.busy) return;
      this.busy = true;
      try {
        await this.homeAssistant.callService("water_heater", "set_temperature", {
          entity_id: this.config.entity, temperature: value
        });
        this.error = "";
      } catch (_error) {
        this.error = "Impossibile confermare la nuova temperatura ACS.";
      } finally {
        this.busy = false;
        this.dragging = false;
        this.render();
      }
    }

    async toggleComfort(current) {
      if (!this.homeAssistant || !this.config || this.busy) return;
      this.busy = true;
      try {
        await this.homeAssistant.callService(
          "switch", current ? "turn_off" : "turn_on",
          {entity_id: this.config.comfort_entity}
        );
        this.error = "";
      } catch (_error) {
        this.error = "Comando Comfort non confermato.";
      } finally {
        this.busy = false;
        this.render();
      }
    }

    render() {
      if (!this.config || !this.shadowRoot) return;
      const hass = this.homeAssistant;
      const heater = hass && hass.states[this.config.entity];
      const comfort = hass && hass.states[this.config.comfort_entity];
      const attrs = heater && heater.attributes || {};
      const number = (raw, fallback) => {
        if (raw === null || raw === undefined || raw === "") return fallback;
        const result = Number(raw);
        return Number.isFinite(result) ? result : fallback;
      };
      const minimum = number(attrs.min_temp, 36);
      const maximum = number(attrs.max_temp, 60);
      const actual = number(attrs.temperature, NaN);
      const good = heater && heater.state !== "unavailable" &&
        Number.isFinite(actual) && minimum < maximum;
      const wrapper = node("ha-card");
      const style = node("style");
      style.textContent = css;
      const header = node("div", "header");
      header.append(node("h2", "", this.config.title));
      header.append(node("span", "value", good ? actual.toFixed(0) + " °C" : "—"));
      wrapper.append(header);
      wrapper.append(node("p", "subtitle", "Imposta la temperatura desiderata"));
      const range = node("input");
      range.type = "range";
      range.min = String(minimum);
      range.max = String(maximum);
      range.step = "1";
      range.value = String(good ? actual : minimum);
      range.disabled = !good || !!this.busy;
      range.setAttribute("aria-label", "Temperatura acqua sanitaria");
      const shown = header.querySelector(".value");
      range.addEventListener("input", () => {
        this.dragging = true;
        shown.textContent = range.value + " °C";
      });
      range.addEventListener("change", () => {
        this.dragging = false;
        const chosen = Number(range.value);
        if (good && Number.isFinite(chosen) && chosen >= minimum &&
            chosen <= maximum && chosen !== actual) {
          void this.commitTemperature(chosen);
        } else {
          this.render();
        }
      });
      wrapper.append(range);
      const limits = node("div", "limits");
      limits.append(node("span", "", minimum + " °C"));
      limits.append(node("span", "", maximum + " °C"));
      wrapper.append(limits);
      const controls = node("div", "controls");
      const button = node("button", "", "Comfort ACS");
      button.type = "button";
      const on = comfort && comfort.state === "on";
      const comfortReady = comfort && ["on", "off"].includes(comfort.state);
      button.disabled = !comfortReady || !!this.busy;
      button.setAttribute("aria-pressed", on ? "true" : "false");
      button.addEventListener("click", () => {
        if (comfortReady) void this.toggleComfort(on);
      });
      controls.append(button);
      if (!comfortReady) controls.append(node("p", "subtitle", "Comfort non disponibile"));
      wrapper.append(controls);
      if (this.error) wrapper.append(node("p", "error", this.error));
      this.shadowRoot.replaceChildren(style, wrapper);
    }
  }

  if (!customElements.get("ariston-cube-acs-card")) {
    customElements.define("ariston-cube-acs-card", AristonCubeAcsCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "ariston-cube-acs-card",
      name: "Ariston Cube · Acqua calda",
      description: "Temperatura sanitaria con pulsante Comfort separato"
    });
  }
})();
