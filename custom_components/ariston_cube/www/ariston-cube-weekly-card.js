/* Ariston Cube weekly card, experimental edit mode (1.1.0-rc.6).
 * Move, insert or delete ONE weekday boundary per save.
 * The backend performs a fresh GET, fingerprint check, ONE POST, full readback.
 * Never send requests directly to Ariston from this Lovelace card.
 */
(function () {
  "use strict";
  const DAYS = [
    ["Lunedì", "Lun", 1], ["Martedì", "Mar", 2],
    ["Mercoledì", "Mer", 3], ["Giovedì", "Gio", 4],
    ["Venerdì", "Ven", 5], ["Sabato", "Sab", 6],
    ["Domenica", "Dom", 0]
  ];
  const css = [
    ":host{display:block;color:var(--primary-text-color)}",
    "ha-card{display:block;padding:20px 18px}",
    ".heading{display:flex;align-items:center;justify-content:space-between;gap:12px}",
    "h2{font-size:1.12rem;font-weight:600;margin:0 0 4px}",
    ".subtitle,.footer,.times{color:var(--secondary-text-color);font-size:.75rem}",
    ".subtitle{margin:0 0 14px}.footer{margin:16px 0 0}",
    ".axis{margin:4px 0 8px 49px;display:flex;justify-content:space-between;font-size:.73rem;color:var(--secondary-text-color)}",
    ".day{display:grid;grid-template-columns:38px minmax(0,1fr);align-items:center;column-gap:11px;padding:9px 0;border-top:1px solid var(--divider-color)}",
    ".day.today .name{font-weight:700;color:var(--primary-color)}",
    ".day.editable{cursor:pointer;border-radius:6px}",
    ".day.selected{background:var(--secondary-background-color)}",
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
    ".btn{border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);padding:8px 12px;border-radius:8px;cursor:pointer;font:inherit}",
    ".btn.primary{background:var(--primary-color);color:var(--text-primary-color,#fff);border-color:var(--primary-color)}",
    ".btn:disabled{opacity:.48;cursor:not-allowed}",
    ".editor{margin-top:16px;padding:14px;border:1px solid var(--divider-color);border-radius:10px}",
    ".editor h3{margin:0 0 12px;font-size:.98rem}",
    ".fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(155px,1fr));gap:10px}",
    ".field{display:flex;flex-direction:column;gap:5px;font-size:.82rem}",
    ".field select,.field input{box-sizing:border-box;width:100%;padding:9px;border:1px solid var(--divider-color);border-radius:7px;background:var(--card-background-color);color:var(--primary-text-color);font:inherit}",
    ".buttons{display:flex;flex-wrap:wrap;gap:9px;margin-top:14px}",
    ".message{margin:12px 0 0;font-size:.82rem;line-height:1.5}",
    ".message.error{color:var(--error-color,#d74343)}",
    ".message.success{color:var(--success-color,#348747)}",
    ".preview{margin-top:12px;border-top:1px solid var(--divider-color);padding-top:12px}",
    ".preview strong{font-size:.86rem}",
    ".preview .line{font-size:.83rem;margin:5px 0}",
    "@media(min-width:700px){.day{grid-template-columns:38px minmax(0,1fr) minmax(190px,1fr)}.times{grid-column:3;margin-left:12px}.bar{height:34px}}"
  ].join("");

  function el(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text != null) item.textContent = String(text);
    return item;
  }
  function time(minute) {
    return String(Math.floor(minute / 60)).padStart(2, "0")
      + ":" + String(minute % 60).padStart(2, "0");
  }
  function parseDay(value) {
    if (typeof value !== "string") return null;
    const points = [];
    const pattern = /(?:^|·)\s*(\d{1,2}):(\d{2})\s+(Comfort|Economy)\b/gi;
    for (const hit of value.matchAll(pattern)) {
      const h = Number(hit[1]), m = Number(hit[2]);
      if (h < 24 && m < 60) points.push({
        minute: h * 60 + m, preset: hit[3].toLowerCase()
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
  function describe(points) {
    return Array.isArray(points)
      ? points.map((p) => p.time + " " + p.preset).join(" · ")
      : "Non disponibile";
  }
  function validTime(value) {
    return typeof value === "string"
      && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value);
  }

  function minuteOf(value) {
    return validTime(value) ? Number(value.slice(0, 2)) * 60
      + Number(value.slice(3, 5)) : null;
  }
  function quarterHour(value) {
    const minute = minuteOf(value);
    return minute !== null && minute % 15 === 0;
  }
  function quarterSelect(value, ariaLabel, onChange) {
    // Some browsers allow arbitrary minutes in input type=time even with
    // step=900. Offer ONLY selectable quarter-hour positions instead.
    const select = el("select");
    select.setAttribute("aria-label", ariaLabel);
    const placeholder = el("option", "", "Seleziona un orario");
    placeholder.value = "";
    select.append(placeholder);
    for (let minute = 15; minute < 1440; minute += 15) {
      const at = time(minute);
      const option = el("option", "", at);
      option.value = at;
      select.append(option);
    }
    select.value = quarterHour(value) && minuteOf(value) > 0 ? value : "";
    select.addEventListener("change", () => onChange(select.value));
    return select;
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
      this.editing = false;
      this.dayIndex = 0;
      this.fromTime = "";
      this.toTime = "";
      this.endTime = "";
      this.operation = "move";
      this.preset = "Comfort";
      this.preview = null;
      this.pending = false;
      this.blocked = false;
      this.message = "";
      this.messageKind = "";
      this.displayedSchedule = "";
      if (this.homeAssistant) this.render();
    }
    set hass(value) {
      this.homeAssistant = value;
      if (this.config) this.render();
    }
    getCardSize() {return this.editing ? 10 : 6;}
    get _weekly() {
      const state = this.homeAssistant?.states?.[this.config.entity];
      return DAYS.map((d) => parseDay(state?.attributes?.[d[0]]));
    }
    get _canEdit() {
      const services = this.homeAssistant?.services?.ariston_cube || {};
      return Boolean(services.preview_weekly_slice && services.test_write_weekly_slice
        && typeof this.homeAssistant.callService === "function");
    }
    get _canAddRemove() {
      const services = this.homeAssistant?.services?.ariston_cube || {};
      return Boolean(this._canEdit
        && services.preview_weekly_change && services.write_weekly_change);
    }
    _invalidatePreview() {
      this.preview = null;
      this.previewRequest = null;
      this.message = "";
      this.messageKind = "";
    }
    _setDay(index) {
      if (this.pending || this.blocked) return;
      const weekly = this._weekly;
      this.dayIndex = index;
      const boundaries = (weekly[index] || []).filter((p) => p.minute > 0);
      this.fromTime = boundaries.length ? time(boundaries[0].minute) : "";
      this.toTime = this.operation === "add" ? "" : this.fromTime;
      this.endTime = "";
      this._invalidatePreview();
      this.key = "";
      this.render();
    }
    _toggleEdit(index = this.dayIndex) {
      if (this.pending) return;
      if (!this._canEdit) return;
      this.editing = !this.editing;
      this.blocked = false;
      this._invalidatePreview();
      if (this.editing) this._setDay(index);
      this.key = "";
      this.render();
    }
    async _invoke(service, data) {
      // Home Assistant's callService signature includes notifyOnError as the
      // fifth argument and returnResponse as the SIXTH argument.
      const result = await this.homeAssistant.callService(
        "ariston_cube", service, data, undefined, false, true
      );
      if (!result || !result.response) {
        throw new Error("Nessuna risposta dall'azione Home Assistant");
      }
      return result.response;
    }
    _changePayload() {
      const operation = this.operation || "move";
      return {
        day: DAYS[this.dayIndex][2], operation,
        from_time: operation === "add" ? "" : this.fromTime,
        to_time: operation === "remove" ? "" : this.toTime,
        end_time: operation === "add" ? this.endTime : "",
        preset: operation === "add" ? this.preset : ""
      };
    }
    _changeIsValid() {
      const kind = this.operation || "move";
      const weekly = this._weekly[this.dayIndex];
      if (!weekly || !weekly.length) return false;
      if (kind === "move") return validTime(this.fromTime)
        && quarterHour(this.toTime) && this.fromTime !== this.toTime
        && this.fromTime !== "00:00" && this.toTime !== "00:00";
      if (!this._canAddRemove) return false;
      if (kind === "add") {
        const start = minuteOf(this.toTime), end = minuteOf(this.endTime);
        if (!quarterHour(this.toTime) || !quarterHour(this.endTime)
            || start <= 0 || end <= start || !["Comfort", "Economy"].includes(this.preset)
            || weekly.some((p) => p.minute === start)
            || weekly.some((p) => start < p.minute && p.minute < end)) return false;
        const preceding = weekly.filter((p) => p.minute < start);
        const oldPreset = preceding.length ? preceding[preceding.length - 1].preset : null;
        if (!oldPreset || oldPreset === this.preset.toLowerCase()) return false;
        const endExists = weekly.some((p) => p.minute === end);
        return weekly.length + (endExists ? 1 : 2) <= 48;
      }
      if (kind === "remove") return validTime(this.fromTime)
        && this.fromTime !== "00:00"
        && weekly.length > 1
        && weekly.some((p) => time(p.minute) === this.fromTime);
      return false;
    }
    async _previewChange() {
      if (this.pending || this.blocked || !this._canEdit) return;
      if (!this._changeIsValid()) {
        this.message = "Controlla l'operazione, l'orario e il preset selezionati.";
        this.messageKind = "error";
        this.key = "";
        this.render();
        return;
      }
      const payload = this._changePayload();
      const snapshot = JSON.stringify(payload);
      const operation = payload.operation;
      this.pending = true;
      this._invalidatePreview();
      this.key = "";
      this.render();
      try {
        const service = operation === "move"
          ? "preview_weekly_slice" : "preview_weekly_change";
        const data = operation === "move" ? {
          day: payload.day, from_time: payload.from_time,
          to_time: payload.to_time
        } : payload;
        const result = await this._invoke(service, data);
        if (result.status !== "preview_only_no_cloud_write"
            || result.changed !== true
            || typeof result.source_fingerprint !== "string"
            || !/^[a-f0-9]{64}$/.test(result.source_fingerprint)
            || result.weekday !== DAYS[this.dayIndex][0]
            || (operation !== "move" && result.operation !== operation)
            || !Array.isArray(result.before) || !Array.isArray(result.after)
            || JSON.stringify(this._changePayload()) !== snapshot) {
          throw new Error("Anteprima non coerente. Nessuna modifica inviata.");
        }
        this.preview = result;
        this.previewRequest = snapshot;
        this.message = "Anteprima letta dal cloud. Controlla gli orari prima di salvare.";
        this.messageKind = "";
      } catch (err) {
        this.message = "Anteprima fallita: " + (err?.message || "errore sconosciuto");
        this.messageKind = "error";
      } finally {
        this.pending = false;
        this.key = "";
        this.render();
      }
    }
    async _saveChange() {
      if (this.pending || this.blocked || !this.preview || !this._canEdit
          || !this._changeIsValid()
          || this.previewRequest !== JSON.stringify(this._changePayload())) return;
      const before = this.preview.before, after = this.preview.after;
      const fingerprint = this.preview.source_fingerprint;
      const weekday = DAYS[this.dayIndex][0];
      if (!Array.isArray(before) || !Array.isArray(after)
          || !/^[a-f0-9]{64}$/.test(fingerprint)) return;
      const confirmation = "Scrivere sul Cube S la modifica di " + weekday
        + "?\n\nPRIMA: " + describe(before) + "\nDOPO: " + describe(after)
        + "\n\nIl salvataggio è reale e non si annulla reinstallando la stable.";
      if (!window.confirm(confirmation)) return;
      this.pending = true;
      this.blocked = true;  // At most one write attempt in this card session.
      this.key = "";
      this.render();
      try {
        const payload = this._changePayload();
        const service = payload.operation === "move"
          ? "test_write_weekly_slice" : "write_weekly_change";
        const data = payload.operation === "move" ? {
          day: payload.day, from_time: payload.from_time,
          to_time: payload.to_time
        } : payload;
        const result = await this._invoke(service, {
          ...data, expected_fingerprint: fingerprint, confirm: true
        });
        if (result.status !== "confirmed_by_fresh_cloud_read" || result.changed !== true) {
          throw new Error("Risposta non confermata. Verifica nell'app Ariston.");
        }
        // The cloud and complete seven-day readback confirmed the change.
        // Unlock ONLY after that confirmation, never on ambiguous failures.
        // Every further modification needs a fresh preview/fingerprint and
        // a new explicit approval; no write is ever retried automatically.
        this._invalidatePreview();
        this.blocked = false;
        this.message = "Modifica confermata dal cloud. Puoi prepararne un'altra "
          + "senza chiudere l'editor: scegli l'operazione e premi di nuovo "
          + "Anteprima. Verifica gli orari aggiornati anche nell'app Ariston.";
        this.messageKind = "success";
      } catch (err) {
        this._invalidatePreview();
        const reason = err?.message || "errore sconosciuto";
        // The dedicated backend prefix is used ONLY when the fresh-read
        // preflight refused the request before any schedule POST. Reopen
        // preview in-place; a new fresh fingerprint is still mandatory.
        if (reason.includes("Nessuna modifica inviata:")) {
          this.blocked = false;
          this.message = reason
            + ". Nessuna scrittura effettuata: correggi la scelta e premi "
            + "di nuovo Anteprima.";
        } else {
          // A request could have reached the Cube S. Never allow another
          // write in the same session after an ambiguous result.
          this.message = "Salvataggio non confermato: " + reason
            + ". Prima di riprovare, controlla la programmazione nell'app Ariston.";
        }
        this.messageKind = "error";
      } finally {
        this.pending = false;
        this.key = "";
        this.render();
      }
    }
    _renderEditor(haCard, weekly) {
      const editor = el("section", "editor");
      editor.append(el("h3", "", "Modifica fasce Cube S"));
      editor.append(el("p", "subtitle",
        "Una sola operazione per salvataggio. Anteprima obbligatoria, poi conferma esplicita sul Cube S."));
      const fields = el("div", "fields");
      const dayField = el("label", "field", "Giorno");
      const daySelect = el("select");
      daySelect.setAttribute("aria-label", "Giorno");
      DAYS.forEach(([label], index) => {
        const opt = el("option", "", label);
        opt.value = String(index);
        daySelect.append(opt);
      });
      daySelect.value = String(this.dayIndex);
      daySelect.disabled = this.pending || this.blocked;
      daySelect.addEventListener("change", () => this._setDay(Number(daySelect.value)));
      dayField.append(daySelect);
      fields.append(dayField);

      if (this._canAddRemove) {
        const opField = el("label", "field", "Operazione");
        const opSelect = el("select");
        opSelect.setAttribute("aria-label", "Operazione");
        for (const [key, label] of [
          ["move", "Sposta orario"],
          ["add", "Aggiungi fascia"],
          ["remove", "Elimina fascia"]
        ]) {
          const opt = el("option", "", label);
          opt.value = key;
          opSelect.append(opt);
        }
        opSelect.value = this.operation;
        opSelect.disabled = this.pending || this.blocked;
        opSelect.addEventListener("change", () => {
          this.operation = opSelect.value;
          const points = (weekly[this.dayIndex] || []).filter((p) => p.minute > 0);
          this.fromTime = points.length ? time(points[0].minute) : "";
          this.toTime = this.operation === "add" ? "" : this.fromTime;
          this.endTime = "";
          this._invalidatePreview();
          this.key = "";
          this.render();
        });
        opField.append(opSelect);
        fields.append(opField);
      }

      const boundaries = (weekly[this.dayIndex] || []).filter((p) => p.minute > 0);
      if (this.operation !== "add") {
        const fromField = el("label", "field",
          this.operation === "remove" ? "Fascia da eliminare" : "Fascia da spostare");
        const fromSelect = el("select");
        fromSelect.setAttribute("aria-label",
          this.operation === "remove" ? "Fascia da eliminare" : "Fascia da spostare");
        if (!boundaries.length) {
          const opt = el("option", "", "Nessuna fascia disponibile");
          opt.value = "";
          fromSelect.append(opt);
        }
        boundaries.forEach((point) => {
          const value = time(point.minute);
          const opt = el("option", "", value + " " + point.preset);
          opt.value = value;
          fromSelect.append(opt);
        });
        if (boundaries.some((point) => time(point.minute) === this.fromTime)) {
          fromSelect.value = this.fromTime;
        }
        fromSelect.disabled = this.pending || this.blocked || !boundaries.length;
        fromSelect.addEventListener("change", () => {
          this.fromTime = fromSelect.value;
          this.toTime = this.fromTime;
          this._invalidatePreview();
          this.key = "";
          this.render();
        });
        fromField.append(fromSelect);
        fields.append(fromField);
      }
      if (this.operation !== "remove") {
        const toField = el("label", "field",
          this.operation === "add" ? "Inizio nuova fascia (ogni 15 min)" : "Nuovo orario (ogni 15 min)");
        const toSelect = quarterSelect(
          this.toTime, "Inizio o nuovo orario (15 minuti)", (value) => {
            this.toTime = value;
            this._invalidatePreview();
            this.key = "";
            this.render();
          }
        );
        toSelect.disabled = this.pending || this.blocked;
        toField.append(toSelect);
        fields.append(toField);
      }
      if (this.operation === "add") {
        const endField = el("label", "field", "Fine nuova fascia (ogni 15 min)");
        const endSelect = quarterSelect(
          this.endTime, "Fine nuova fascia (15 minuti)", (value) => {
            this.endTime = value;
            this._invalidatePreview();
            this.key = "";
            this.render();
          }
        );
        endSelect.disabled = this.pending || this.blocked;
        endField.append(endSelect);
        fields.append(endField);
        editor.append(el("p", "subtitle",
          "Alla fine torna la modalità originale. Non sono ammesse sovrapposizioni."));
      }
      if (this.operation === "add") {
        const presetField = el("label", "field", "Modalità nuova fascia");
        const presetSelect = el("select");
        presetSelect.setAttribute("aria-label", "Modalità nuova fascia");
        for (const preset of ["Comfort", "Economy"]) {
          const option = el("option", "", preset);
          option.value = preset;
          presetSelect.append(option);
        }
        presetSelect.value = this.preset;
        presetSelect.disabled = this.pending || this.blocked;
        presetSelect.addEventListener("change", () => {
          this.preset = presetSelect.value;
          this._invalidatePreview();
          this.key = "";
          this.render();
        });
        presetField.append(presetSelect);
        fields.append(presetField);
      }

      editor.append(fields);
      const actions = el("div", "buttons");
      const previewBtn = el("button", "btn primary", this.pending ? "Operazione in corso…" : "Anteprima");
      previewBtn.type = "button";
      previewBtn.disabled = this.pending || this.blocked || !this._changeIsValid();
      previewBtn.addEventListener("click", () => this._previewChange());
      actions.append(previewBtn);
      const saveBtn = el("button", "btn", "Salva sul Cube S");
      saveBtn.type = "button";
      saveBtn.disabled = this.pending || this.blocked || !this.preview
        || this.preview.changed !== true || !this._changeIsValid();
      saveBtn.addEventListener("click", () => this._saveChange());
      actions.append(saveBtn);
      editor.append(actions);
      if (this.preview) {
        const previewBox = el("div", "preview");
        previewBox.append(el("strong", "", "Anteprima dal cloud — " + this.preview.weekday));
        previewBox.append(el("p", "line", "Prima: " + describe(this.preview.before)));
        previewBox.append(el("p", "line", "Dopo: " + describe(this.preview.after)));
        editor.append(previewBox);
      }
      if (this.message) {
        const message = el("p", "message " + this.messageKind, this.message);
        message.setAttribute("role", this.messageKind === "error" ? "alert" : "status");
        editor.append(message);
      }
      if (this.blocked) {
        editor.append(el("p", "footer",
          "Sessione di modifica conclusa. Verifica l'app Ariston prima di riaprire l'editor."));
      }
      haCard.append(editor);
    }
    render() {
      if (!this.homeAssistant || !this.config) return;
      const state = this.homeAssistant.states?.[this.config.entity];
      const values = DAYS.map((d) => state?.attributes?.[d[0]]);
      const scheduleKey = JSON.stringify(values);
      if (this.preview && this.displayedSchedule && this.displayedSchedule !== scheduleKey) {
        this._invalidatePreview(); // A live schedule update invalidates approval.
      }
      this.displayedSchedule = scheduleKey;
      const current = JSON.stringify([state?.state, values, this.config.title,
        this.editing, this.dayIndex, this.operation, this.fromTime, this.toTime,
        this.endTime, this.preset,
        Boolean(this.preview), this.pending, this.blocked,
        this.message, this.messageKind, this._canEdit]);
      if (this.key === current) return;
      this.key = current;
      const weekly = values.map(parseDay);
      const activeDay = (new Date().getDay() + 6) % 7;
      const root = this.shadowRoot;
      const style = el("style"); style.textContent = css;
      const haCard = el("ha-card");
      const heading = el("div", "heading");
      heading.append(el("h2", "", this.config.title));
      if (this._canEdit) {
        const toggle = el("button", "btn", this.editing ? "Chiudi editor" : "Modifica fasce");
        toggle.type = "button";
        toggle.disabled = this.pending;
        toggle.addEventListener("click", () => this._toggleEdit());
        heading.append(toggle);
      }
      haCard.append(heading);
      haCard.append(el("p", "subtitle", "Programmazione reale del Cube S"));
      if (!state) haCard.append(el("p", "subtitle", "Sensore non disponibile: " + this.config.entity));
      const axis = el("div", "axis");
      for (const hour of ["00", "06", "12", "18", "24"]) axis.append(el("span", "", hour));
      haCard.append(axis);
      DAYS.forEach(([name, short], index) => {
        const editable = this._canEdit && !this.pending && !this.blocked;
        const row = el("div", "day" + (index === activeDay ? " today" : "")
          + (editable ? " editable" : "")
          + (this.editing && index === this.dayIndex ? " selected" : ""));
        row.append(el("span", "name", short));
        const bar = el("div", "bar");
        const slices = intervals(weekly, index);
        if (slices) slices.forEach((period) => {
          const segment = el("span", "segment " + period.preset);
          segment.style.left = (period.start / 1440 * 100) + "%";
          segment.style.width = ((period.end - period.start) / 1440 * 100) + "%";
          segment.title = time(period.start) + "–" + time(period.end) + " " + period.preset;
          bar.append(segment);
        });
        row.append(bar);
        row.append(el("p", "times", values[index] || "Nessun programma disponibile"));
        if (editable) {
          row.tabIndex = 0;
          row.setAttribute("role", "button");
          row.setAttribute("aria-label", "Modifica fasce di " + name);
          const selectDay = () => {
            if (!this.editing) this._toggleEdit(index);
            else this._setDay(index);
          };
          row.addEventListener("click", selectDay);
          row.addEventListener("keydown", (event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              selectDay();
            }
          });
        }
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
      if (this.editing && this._canEdit) this._renderEditor(haCard, weekly);
      haCard.append(el("p", "footer",
        this._canEdit
          ? "Premi un giorno o «Modifica fasce». Il salvataggio richiede anteprima e conferma."
          : "Sola lettura: le fasce originali restano gestite dal Cube S."));
      root.replaceChildren(style, haCard);
    }
  }
  if (!customElements.get("ariston-cube-weekly-card")) {
    customElements.define("ariston-cube-weekly-card", AristonCubeWeeklyCard);
    window.customCards = window.customCards || [];
    window.customCards.push({
      type: "ariston-cube-weekly-card",
      name: "Ariston Cube · Settimana Comfort/Economy",
      description: "Timeline settimanale con editor per spostare, aggiungere o eliminare fasce"
    });
  }
})();
