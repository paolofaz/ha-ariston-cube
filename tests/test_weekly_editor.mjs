/* Behavioral smoke tests for the experimental Lovelace card.
 * Uses only Node built-ins and a minimal fake DOM; no browser or boiler.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

const script = fs.readFileSync(
  "custom_components/ariston_cube/www/ariston-cube-weekly-card.js", "utf8"
);
const validFingerprint = "a".repeat(64);
const initial = {
  "Lunedì": "00:00 Economy · 06:00 Comfort · 21:30 Economy",
  "Martedì": "00:00 Economy · 05:45 Comfort · 21:30 Economy",
  "Mercoledì": "00:00 Economy · 05:45 Comfort · 21:30 Economy",
  "Giovedì": "00:00 Economy · 05:45 Comfort · 21:30 Economy",
  "Venerdì": "00:00 Economy · 05:45 Comfort · 21:30 Economy",
  "Sabato": "00:00 Economy · 07:00 Comfort · 18:00 Economy",
  "Domenica": "00:00 Economy · 07:00 Comfort · 18:00 Economy",
};

function makeCard({
  enabled = true, approve = true, writeError = null,
  newEditor = false, cloneEditor = false
} = {}) {
  class Element {
    constructor(tag = "custom") {
      this.tag = tag;
      this.children = [];
      this.style = {};
      this.listeners = {};
      this.attributes = {};
    }
    append(...items) {this.children.push(...items);}
    replaceChildren(...items) {this.children = [...items];}
    addEventListener(type, callback) {this.listeners[type] = callback;}
    setAttribute(key, value) {this.attributes[key] = value;}
    attachShadow() {
      this.shadowRoot = new Element("shadow");
      return this.shadowRoot;
    }
  }
  const registry = new Map();
  const browser = {
    customCards: [],
    prompts: [],
    confirm(message) {this.prompts.push(message); return approve;},
  };
  vm.runInNewContext(script, {
    HTMLElement: Element,
    customElements: {
      get: (name) => registry.get(name),
      define: (name, klass) => registry.set(name, klass),
    },
    document: {
      createElement: (tag) => new Element(tag),
      createTextNode: (text) => {
        const node = new Element("#text");
        node.textContent = text;
        return node;
      },
    },
    window: browser,
  }, {timeout: 3000});
  const Klass = registry.get("ariston-cube-weekly-card");
  assert.ok(Klass);
  const card = new Klass();
  card.setConfig({entity: "sensor.cube_weekly", title: "Settimana Cube S"});
  const calls = [];
  const hass = {
    states: {"sensor.cube_weekly": {state: "Disponibile", attributes: {...initial}}},
    services: enabled ? {ariston_cube: {
      preview_weekly_change: {},
      write_weekly_change: {},
      ...(cloneEditor ? {preview_weekly_clone: {}, clone_weekly_days: {}} : {}),
    }} : {},
    async callService(...args) {
      calls.push(args);
      const service = args[1];
      if (service === "preview_weekly_clone") {
        const {source_day, destinations} = args[2];
        const dayNames = [
          "Domenica", "Lunedì", "Martedì", "Mercoledì",
          "Giovedì", "Venerdì", "Sabato"
        ];
        const sourceSchedule = [
          {minute: 0, time: "00:00", preset: "Economy"},
          {minute: 360, time: "06:00", preset: "Comfort"},
          {minute: 1290, time: "21:30", preset: "Economy"},
        ];
        const oldSchedule = [
          {minute: 0, time: "00:00", preset: "Economy"},
          {minute: 420, time: "07:00", preset: "Comfort"},
          {minute: 1080, time: "18:00", preset: "Economy"},
        ];
        const before = {}, after = {};
        for (const day of destinations) {
          before[dayNames[day]] = oldSchedule;
          after[dayNames[day]] = sourceSchedule;
        }
        return {response: {
          status: "preview_only_no_cloud_write",
          kind: "clone", changed: true, can_submit: false,
          source_day, source_weekday: dayNames[source_day],
          destinations, destination_weekdays: destinations.map((d) => dayNames[d]),
          changed_destinations: destinations,
          changed_weekdays: destinations.map((d) => dayNames[d]),
          source_schedule: sourceSchedule, before, after,
          source_fingerprint: validFingerprint,
        }};
      }
      if (service === "clone_weekly_days") {
        if (writeError) throw new Error(writeError);
        return {response: {
          status: "confirmed_by_fresh_cloud_read", operation: "clone",
          changed: true,
        }};
      }
      if (service === "preview_weekly_change" && args[2].operation === "move") {
        return {response: {
          status: "preview_only_no_cloud_write", weekday: "Lunedì",
          operation: "move",
          before: [
            {minute: 0, time: "00:00", preset: "Economy"},
            {minute: 360, time: "06:00", preset: "Comfort"},
            {minute: 1290, time: "21:30", preset: "Economy"},
          ],
          after: [
            {minute: 0, time: "00:00", preset: "Economy"},
            {minute: 375, time: "06:15", preset: "Comfort"},
            {minute: 1290, time: "21:30", preset: "Economy"},
          ],
          changed: true, can_submit: false,
          source_fingerprint: validFingerprint,
        }};
      }
      if (service === "preview_weekly_change") {
        const payload = args[2];
        const before = [
          {minute: 0, time: "00:00", preset: "Economy"},
          {minute: 360, time: "06:00", preset: "Comfort"},
          {minute: 1290, time: "21:30", preset: "Economy"},
        ];
        let after;
        if (payload.operation === "add") {
          after = [
            before[0], before[1],
            {minute: 720, time: "12:00", preset: "Economy"},
            {minute: 780, time: "13:00", preset: "Comfort"},
            before[2],
          ];
        } else if (payload.operation === "remove") {
          after = [before[0]];
        } else throw new Error("Unexpected mutation");
        return {response: {
          status: "preview_only_no_cloud_write", weekday: "Lunedì",
          operation: payload.operation, before, after, changed: true,
          can_submit: false, source_fingerprint: validFingerprint,
        }};
      }
      if (service === "write_weekly_change") {
        if (writeError) throw new Error(writeError);
        return {response: {
          status: "confirmed_by_fresh_cloud_read", changed: true,
        }};
      }
      throw new Error("Unexpected service " + service);
    },
  };
  card.hass = hass;
  return {card, calls, hass, browser};
}

test("stable without experimental services remains a readable timeline", () => {
  const {card} = makeCard({enabled: false});
  assert.equal(card._canEdit, false);
  card._toggleEdit();
  assert.equal(card.editing, false);
  assert.equal(card.getCardSize(), 6);
  assert.ok(card.shadowRoot.children.length);
});

test("weekday tap opens editor, preview is read-only, then save is one write", async () => {
  const {card, calls} = makeCard();
  assert.equal(card._canEdit, true);
  card._toggleEdit(0);
  assert.equal(card.editing, true);
  assert.equal(card.fromTime, "06:00");
  assert.equal(card.getCardSize(), 10);
  card.toTime = "06:15";
  await card._previewChange();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "ariston_cube");
  assert.equal(calls[0][1], "preview_weekly_change");
  assert.equal(calls[0][3], undefined);
  assert.equal(calls[0][4], false);
  assert.equal(calls[0][5], true);
  assert.equal(card.preview.source_fingerprint, validFingerprint);
  assert.equal(card.blocked, false);
  await card._saveChange();
  assert.equal(calls.length, 2);
  assert.equal(calls[1][1], "write_weekly_change");
  assert.equal(calls[1][2].expected_fingerprint, validFingerprint);
  assert.equal(calls[1][2].confirm, true);
  assert.equal(calls[1][2].day, 1);
  assert.equal(calls[1][2].from_time, "06:00");
  assert.equal(calls[1][2].to_time, "06:15");
  assert.equal(card.blocked, false, "Confirmed save unlocks the next preview");
  assert.equal(card.preview, null, "The previous fingerprint is consumed");
  assert.equal(card.messageKind, "success");
  await card._saveChange();
  assert.equal(calls.length, 2, "Never reuse a consumed preview");

});

test("cancelling the real write never calls the write service", async () => {
  const {card, calls} = makeCard({approve: false});
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  await card._saveChange();
  assert.equal(calls.length, 1);
  assert.equal(card.blocked, false);
});

test("a failed write blocks a second attempt in that session", async () => {
  const {card, calls} = makeCard({writeError: "HTTP 400"});
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  await card._saveChange();
  assert.equal(card.blocked, true);
  assert.equal(card.messageKind, "error");
  assert.match(card.message, /HTTP 400/);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 1);
});

test("a schedule update invalidates the previous cloud fingerprint", async () => {
  const {card, hass, calls} = makeCard();
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  assert.ok(card.preview);
  hass.states["sensor.cube_weekly"].attributes["Lunedì"]
    = "00:00 Economy · 06:15 Comfort · 21:30 Economy";
  card.hass = hass;
  assert.equal(card.preview, null);
  await card._saveChange();
  assert.equal(calls.length, 1);
});

test("changing day or time clears the staged write", async () => {
  const {card} = makeCard();
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  assert.ok(card.preview);
  card._setDay(1);
  assert.equal(card.preview, null);
  assert.equal(card.fromTime, "05:45");
  assert.equal(card.toTime, "05:45");
});


test("single definitive backend exposes move add remove actions", () => {
  const original = makeCard();
  assert.equal(original.card._canAddRemove, true);
  const {card} = makeCard({newEditor: true});
  assert.equal(card._canAddRemove, true);
  card._toggleEdit(0);
  const editorText = card.shadowRoot.children
    .flatMap((x) => x.children || [])
    .map((x) => x.textContent || "").join(" ");
  assert.ok(card.editing);
  assert.ok(editorText.includes("Modifica"));
});

test("adding a Comfort/Economy boundary requires preview and one write", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  assert.equal(card._changeIsValid(), true);
  await card._previewChange();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "preview_weekly_change");
  assert.equal(calls[0][2].operation, "add");
  assert.equal(calls[0][2].to_time, "12:00");
  assert.equal(calls[0][2].end_time, "13:00");
  assert.equal(calls[0][2].preset, "Economy");
  assert.equal(card.preview.after.length, 5);
  assert.equal(card.preview.after[3].time, "13:00");
  assert.equal(card.preview.after[3].preset, "Comfort");
  await card._saveChange();
  assert.equal(calls.length, 2);
  assert.equal(calls[1][1], "write_weekly_change");
  assert.equal(calls[1][2].operation, "add");
  assert.equal(calls[1][2].end_time, "13:00");
  assert.equal(calls[1][2].expected_fingerprint, validFingerprint);
  assert.equal(calls[1][2].confirm, true);
  assert.equal(card.blocked, false, "Confirmed save unlocks the next preview");
  assert.equal(card.preview, null, "The previous fingerprint is consumed");
  assert.equal(card.messageKind, "success");
  await card._saveChange();
  assert.equal(calls.length, 2, "Never reuse a consumed preview");

});

test("removal preview shows resulting schedule and sends one confirmed POST", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "remove";
  card.fromTime = "06:00";
  assert.equal(card._changeIsValid(), true);
  await card._previewChange();
  assert.equal(card.preview.before.length, 3);
  assert.equal(card.preview.after.length, 1);
  await card._saveChange();
  assert.equal(calls[1][1], "write_weekly_change");
  assert.equal(calls[1][2].from_time, "06:00");
  assert.equal(calls[1][2].to_time, "");
  assert.equal(calls[1][2].end_time, "");
  assert.equal(calls[1][2].preset, "");
  assert.equal(calls.filter((call) => call[1] === "write_weekly_change").length, 1);
});

test("changing operation or preset invalidates staged approval", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  await card._previewChange();
  assert.ok(card.preview);
  card.preset = "Comfort";
  await card._saveChange();
  assert.equal(calls.length, 1, "No POST for changed preset");
  card.preset = "Economy";
  card.operation = "remove";
  await card._saveChange();
  assert.equal(calls.length, 1, "No POST for changed operation");
});

test("invalid new boundaries never send a cloud request", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "00:00";
  await card._previewChange();
  assert.equal(calls.length, 0);
  card.toTime = "06:00";
  await card._previewChange();
  assert.equal(calls.length, 0);
  card.operation = "remove";
  card.fromTime = "00:00";
  await card._previewChange();
  assert.equal(calls.length, 0);
});

test("failed add or remove write blocks repeating in the same UI session", async () => {
  const {card, calls} = makeCard({newEditor: true, writeError: "HTTP 400"});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  await card._previewChange();
  await card._saveChange();
  assert.equal(card.blocked, true);
  assert.equal(card.messageKind, "error");
  await card._saveChange();
  assert.equal(calls.filter((call) => call[1] === "write_weekly_change").length, 1);
});


test("two verified changes can be staged sequentially without closing editor", async () => {
  const {card, calls, hass} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  await card._saveChange();
  assert.equal(card.blocked, false);
  assert.equal(card.editing, true);
  assert.equal(card.preview, null);
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 1);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 1);

  // Simulate the HA coordinator publishing the cloud-confirmed changed day.
  hass.states["sensor.cube_weekly"].attributes["Lunedì"]
    = "00:00 Economy · 06:15 Comfort · 21:30 Economy";
  card.hass = hass;
  card.operation = "remove";
  card.fromTime = "06:15";
  card.toTime = "06:15";
  await card._previewChange();
  assert.ok(card.preview);
  assert.equal(calls.filter((x) => x[1] === "preview_weekly_change").length, 2);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 2);
  assert.equal(card.blocked, false);
  assert.equal(card.preview, null);
});


test("known preflight refusal can be corrected in-place without another POST", async () => {
  const {card, calls} = makeCard({
    newEditor: true,
    writeError: "Nessuna modifica inviata: Unknown zone metadata",
  });
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  await card._previewChange();
  await card._saveChange();
  assert.equal(card.blocked, false, "Refused pre-POST requests are safe to re-preview");
  assert.equal(card.preview, null);
  assert.equal(card.editing, true);
  assert.match(card.message, /Nessuna modifica inviata/);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 1);
  await card._previewChange();
  assert.equal(calls.filter((x) => x[1] === "preview_weekly_change").length, 2);
});


test("finite additions require both start and end and reject non-quarter times", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.preset = "Economy";
  assert.equal(card._changeIsValid(), false, "No default end at midnight");
  await card._previewChange();
  assert.equal(calls.length, 0, "No request without explicit end");
  card.endTime = "12:00";
  assert.equal(card._changeIsValid(), false);
  card.endTime = "11:45";
  assert.equal(card._changeIsValid(), false);
  card.endTime = "13:07";
  assert.equal(card._changeIsValid(), false);
  card.toTime = "12:07";
  card.endTime = "13:00";
  assert.equal(card._changeIsValid(), false);
  card.toTime = "12:00";
  card.endTime = "22:00";
  assert.equal(card._changeIsValid(), false, "Cannot cross existing 21:30 boundary");
  card.endTime = "13:00";
  assert.equal(card._changeIsValid(), true);
  await card._previewChange();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][2].to_time, "12:00");
  assert.equal(calls[0][2].end_time, "13:00");
});

test("quarter-hour dropdowns offer only 00 15 30 45 minute choices", () => {
  const {card} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  card.key = "";
  card.render();

  function collect(node) {
    const matches = [];
    if (node.tag === "select") matches.push(node);
    for (const child of node.children || []) matches.push(...collect(child));
    return matches;
  }
  const selects = collect(card.shadowRoot);
  const byLabel = (label) => selects.find((item) => item.attributes["aria-label"] === label);
  const start = byLabel("Inizio o nuovo orario (15 minuti)");
  const end = byLabel("Fine nuova fascia (15 minuti)");
  assert.ok(start);
  assert.ok(end);
  for (const select of [start, end]) {
    const values = select.children.map((opt) => opt.value).filter(Boolean);
    assert.equal(values.length, 95);
    assert.ok(values.includes("12:00"));
    assert.ok(values.includes("12:15"));
    assert.ok(values.includes("12:30"));
    assert.ok(values.includes("12:45"));
    assert.ok(!values.includes("12:07"));
    assert.ok(!values.includes("24:00"));
    assert.ok(values.every((value) => [0, 15, 30, 45].includes(
      Number(value.split(":")[1]))));
  }
});

test("changing only the end time invalidates a saved preview fingerprint", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
  card.endTime = "13:00";
  card.preset = "Economy";
  await card._previewChange();
  assert.ok(card.preview);
  card.endTime = "13:15";
  await card._saveChange();
  assert.equal(calls.length, 1, "Cannot save old preview with changed end");
});


test("cloning Monday to Wednesday, Friday and Sunday previews and POSTS once", async () => {
  const {card, calls, browser} = makeCard({newEditor: true, cloneEditor: true});
  assert.equal(card._canClone, true);
  card._toggleEdit(0);  // Monday index 0 / Ariston day 1
  card.operation = "clone";
  card.cloneTargets = [2, 4, 6];  // Wed, Fri, Sun
  assert.equal(card._changeIsValid(), true);
  await card._previewChange();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "preview_weekly_clone");
  assert.equal(calls[0][2].source_day, 1);
  assert.deepEqual(calls[0][2].destinations, [0, 3, 5]);
  assert.equal(card.preview.source_weekday, "Lunedì");
  assert.equal(card.preview.destination_weekdays.length, 3);
  await card._saveChange();
  assert.equal(calls.length, 2, "All clone targets in ONE POST");
  assert.equal(calls[1][1], "clone_weekly_days");
  assert.equal(calls[1][2].source_day, 1);
  assert.deepEqual(calls[1][2].destinations, [0, 3, 5]);
  assert.equal(calls[1][2].expected_fingerprint, validFingerprint);
  assert.equal(calls[1][2].confirm, true);
  assert.equal(browser.prompts.length, 1);
  for (const day of ["Lunedì", "Mercoledì", "Venerdì", "Domenica"]) {
    assert.ok(browser.prompts[0].includes(day));
  }
  assert.ok(browser.prompts[0].includes("\nPRIMA: "), "popup has readable newlines");
  assert.ok(!browser.prompts[0].includes("reinstallando la stable"));
  assert.equal(card.preview, null, "Preview consumed after save");
  assert.equal(card.blocked, false, "Confirmed success permits new preview");
  await card._saveChange();
  assert.equal(calls.length, 2);
});


test("clone requires destinations distinct from the source", async () => {
  const {card, calls} = makeCard({newEditor: true, cloneEditor: true});
  card._toggleEdit(0);
  card.operation = "clone";
  assert.equal(card._changeIsValid(), false);
  await card._previewChange();
  assert.equal(calls.length, 0);
  card.cloneTargets = [0]; // the selected source
  assert.equal(card._changeIsValid(), false);
  card.cloneTargets = [2, 2];
  assert.equal(card._changeIsValid(), false);
  card.cloneTargets = [2, 4];
  assert.equal(card._changeIsValid(), true);
});


test("selection checkboxes include six targets but never the source", () => {
  const {card} = makeCard({newEditor: true, cloneEditor: true});
  card._toggleEdit(0);
  card.operation = "clone";
  card.key = "";
  card.render();
  function walk(node) {
    let list = node.tag === "input" && node.type === "checkbox" ? [node] : [];
    for (const child of node.children || []) list.push(...walk(child));
    return list;
  }
  const checkboxes = walk(card.shadowRoot);
  assert.equal(checkboxes.length, 6);
  assert.equal(checkboxes.some((x) => x.attributes["aria-label"] === "Clona su Lunedì"), false);
  const wed = checkboxes.find((x) => x.attributes["aria-label"] === "Clona su Mercoledì");
  const fri = checkboxes.find((x) => x.attributes["aria-label"] === "Clona su Venerdì");
  wed.checked = true;
  wed.listeners.change();
  fri.checked = true;
  fri.listeners.change();
  assert.deepEqual(Array.from(card.cloneTargets), [2, 4]);
  assert.equal(card._changeIsValid(), true);
});


test("changing clone destinations or source invalidates preview approval", async () => {
  const {card, calls} = makeCard({newEditor: true, cloneEditor: true});
  card._toggleEdit(0);
  card.operation = "clone";
  card.cloneTargets = [2, 4, 6];
  await card._previewChange();
  assert.ok(card.preview);
  card.cloneTargets = [2, 4];
  await card._saveChange();
  assert.equal(calls.length, 1);
  card._setDay(1); // Tuesday
  assert.deepEqual(Array.from(card.cloneTargets), []);
  assert.equal(card.preview, null);
});


test("clone cancelled confirmation never sends a write", async () => {
  const {card, calls} = makeCard({
    newEditor: true, cloneEditor: true, approve: false
  });
  card._toggleEdit(0);
  card.operation = "clone";
  card.cloneTargets = [2, 4];
  await card._previewChange();
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "clone_weekly_days").length, 0);
  assert.equal(card.blocked, false);
});


test("ambiguous clone failure does not retry or unlock writes", async () => {
  const {card, calls} = makeCard({
    newEditor: true, cloneEditor: true, writeError: "Cloud timeout"
  });
  card._toggleEdit(0);
  card.operation = "clone";
  card.cloneTargets = [2, 4, 6];
  await card._previewChange();
  await card._saveChange();
  assert.equal(card.blocked, true);
  assert.equal(card.messageKind, "error");
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "clone_weekly_days").length, 1);
});


test("ordinary time-move popup no longer mentions reinstalling stable", async () => {
  const {card, browser} = makeCard();
  card._toggleEdit(0);
  card.toTime = "06:15";
  await card._previewChange();
  await card._saveChange();
  assert.ok(browser.prompts[0].includes("PRIMA: "));
  assert.ok(browser.prompts[0].includes("DOPO: "));
  assert.ok(!browser.prompts[0].includes("reinstallando la stable"));
});
