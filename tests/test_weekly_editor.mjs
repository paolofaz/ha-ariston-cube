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

function makeCard({enabled = true, approve = true, writeError = null, newEditor = false} = {}) {
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
    confirm() {return approve;},
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
      preview_weekly_slice: {},
      test_write_weekly_slice: {},
      ...(newEditor ? {preview_weekly_change: {}, write_weekly_change: {}} : {}),
    }} : {},
    async callService(...args) {
      calls.push(args);
      const service = args[1];
      if (service === "preview_weekly_slice") {
        return {response: {
          status: "preview_only_no_cloud_write", weekday: "Lunedì",
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
            before[2],
          ];
        } else if (payload.operation === "remove") {
          after = [before[0], before[2]];
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
      if (service === "test_write_weekly_slice") {
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
  assert.equal(calls[0][1], "preview_weekly_slice");
  assert.equal(calls[0][3], undefined);
  assert.equal(calls[0][4], false);
  assert.equal(calls[0][5], true);
  assert.equal(card.preview.source_fingerprint, validFingerprint);
  assert.equal(card.blocked, false);
  await card._saveChange();
  assert.equal(calls.length, 2);
  assert.equal(calls[1][1], "test_write_weekly_slice");
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
  assert.equal(calls.filter((x) => x[1] === "test_write_weekly_slice").length, 1);
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


test("new card exposes add and remove actions only with backend support", () => {
  const original = makeCard();
  assert.equal(original.card._canAddRemove, false);
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
  card.preset = "Economy";
  assert.equal(card._changeIsValid(), true);
  await card._previewChange();
  assert.equal(calls.length, 1);
  assert.equal(calls[0][1], "preview_weekly_change");
  assert.equal(calls[0][2].operation, "add");
  assert.equal(calls[0][2].to_time, "12:00");
  assert.equal(calls[0][2].preset, "Economy");
  assert.equal(card.preview.after.length, 4);
  await card._saveChange();
  assert.equal(calls.length, 2);
  assert.equal(calls[1][1], "write_weekly_change");
  assert.equal(calls[1][2].operation, "add");
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
  assert.equal(card.preview.after.length, 2);
  await card._saveChange();
  assert.equal(calls[1][1], "write_weekly_change");
  assert.equal(calls[1][2].from_time, "06:00");
  assert.equal(calls[1][2].to_time, "");
  assert.equal(calls[1][2].preset, "");
  assert.equal(calls.filter((call) => call[1] === "write_weekly_change").length, 1);
});

test("changing operation or preset invalidates staged approval", async () => {
  const {card, calls} = makeCard({newEditor: true});
  card._toggleEdit(0);
  card.operation = "add";
  card.toTime = "12:00";
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
  assert.equal(calls.filter((x) => x[1] === "test_write_weekly_slice").length, 1);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "test_write_weekly_slice").length, 1);

  // Simulate the HA coordinator publishing the cloud-confirmed changed day.
  hass.states["sensor.cube_weekly"].attributes["Lunedì"]
    = "00:00 Economy · 06:15 Comfort · 21:30 Economy";
  card.hass = hass;
  card.operation = "remove";
  card.fromTime = "06:15";
  card.toTime = "06:15";
  await card._previewChange();
  assert.ok(card.preview);
  assert.equal(calls.filter((x) => x[1] === "preview_weekly_change").length, 1);
  await card._saveChange();
  assert.equal(calls.filter((x) => x[1] === "write_weekly_change").length, 1);
  assert.equal(card.blocked, false);
  assert.equal(card.preview, null);
});
