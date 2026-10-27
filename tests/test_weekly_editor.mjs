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

function makeCard({enabled = true, approve = true, writeError = null} = {}) {
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
  assert.equal(card.blocked, true);
  assert.equal(card.messageKind, "success");
  await card._saveChange();
  assert.equal(calls.length, 2);
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
