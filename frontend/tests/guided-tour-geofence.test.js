import assert from "node:assert/strict";
import test from "node:test";

import { createArrivalGeofence } from "../src/features/guided-tour/composables/useArrivalGeofence.js";

const center = { longitude: 120, latitude: 31 };
const stops = [{
  stop_id: "buddha",
  attraction_name: "灵山大佛",
  ...center,
  trigger_radius_m: 35,
  dwell_ms: 3000,
}];

function northByMeters(meters) {
  return { longitude: 120, latitude: 31 + meters / 111195.0802335, source: "simulation" };
}

test("geofence requires three continuous seconds inside the 35 meter boundary", () => {
  const geofence = createArrivalGeofence(stops);
  assert.equal(geofence.update(northByMeters(35.1), 0), null);
  assert.equal(geofence.dwellProgress.value, 0);

  assert.equal(geofence.update(northByMeters(35), 100), null);
  assert.equal(geofence.update(northByMeters(34.9), 2999), null);
  assert.equal(geofence.update(northByMeters(34.9), 3100)?.stop_id, "buddha");
  assert.equal(geofence.dwellProgress.value, 1);
});

test("leaving the radius clears dwell and a handled stop does not repeat", () => {
  const geofence = createArrivalGeofence(stops);
  geofence.update(northByMeters(10), 0);
  geofence.update(northByMeters(10), 2000);
  geofence.update(northByMeters(50), 2100);
  assert.equal(geofence.dwellProgress.value, 0);
  geofence.update(northByMeters(10), 3000);
  assert.equal(geofence.update(northByMeters(10), 5900), null);
  const triggered = geofence.update(northByMeters(10), 6000);
  assert.equal(triggered.stop_id, "buddha");
  assert.equal(geofence.update(northByMeters(10), 10000), null);
  assert.deepEqual([...geofence.triggeredIds.value], ["buddha"]);

  geofence.reset();
  assert.equal(geofence.triggeredIds.value.size, 0);
  geofence.update(northByMeters(10), 11000);
  assert.equal(geofence.update(northByMeters(10), 14000)?.stop_id, "buddha");
});

test("GPS with accuracy worse than the stop radius cannot accumulate dwell", () => {
  const geofence = createArrivalGeofence(stops);
  const inaccurate = { ...center, source: "gps", accuracy: 80 };
  geofence.update(inaccurate, 0);
  assert.equal(geofence.update(inaccurate, 4000), null);
  assert.equal(geofence.dwellProgress.value, 0);
});

test("overlapping geofences prefer route order before distance", () => {
  const geofence = createArrivalGeofence([
    { ...stops[0], stop_id: "first", longitude: 120.0001 },
    { ...stops[0], stop_id: "second", longitude: 120 },
  ]);
  geofence.update(center, 0);
  assert.equal(geofence.nearestStop.value.stop_id, "first");
  assert.equal(geofence.update(center, 3000)?.stop_id, "first");
});
