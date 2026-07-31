import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";

import { createLocationProvider } from "../src/features/guided-tour/composables/useLocationProvider.js";

function geolocationDouble() {
  let success;
  let failure;
  const cleared = [];
  return {
    api: {
      watchPosition(onSuccess, onFailure) {
        success = onSuccess;
        failure = onFailure;
        return 17;
      },
      clearWatch(id) {
        cleared.push(id);
      },
    },
    succeed(coords) {
      success?.({ coords, timestamp: 1234 });
    },
    fail(code = 1) {
      failure?.({ code });
    },
    cleared,
  };
}

test("location provider defaults to simulation without requesting permission", async () => {
  const simulationPosition = ref({
    longitude: 120.1,
    latitude: 31.5,
    heading: 45,
    timestamp: 10,
    source: "simulation",
  });
  let requested = 0;
  const provider = createLocationProvider({
    simulationPosition,
    geolocation: { watchPosition() { requested += 1; } },
  });

  assert.equal(provider.mode.value, "simulation");
  assert.equal(provider.position.value.longitude, 120.1);
  assert.equal(requested, 0);
  provider.dispose();
});

test("GPS uses the shared position contract and filters low accuracy for arrivals", async () => {
  const fake = geolocationDouble();
  const provider = createLocationProvider({
    simulationPosition: ref({ longitude: 120, latitude: 31, source: "simulation" }),
    geolocation: fake.api,
    maximumArrivalAccuracy: 35,
  });

  await provider.requestGps();
  assert.equal(provider.mode.value, "gps");
  assert.equal(provider.gpsStatus.value, "requesting");
  fake.succeed({ longitude: 120.2, latitude: 31.6, accuracy: 80, heading: 90, speed: 1 });
  assert.equal(provider.gpsStatus.value, "low_accuracy");
  assert.equal(provider.position.value.source, "gps");
  assert.equal(provider.arrivalPosition.value, null);

  fake.succeed({ longitude: 120.2, latitude: 31.6, accuracy: 12, heading: 90, speed: 1 });
  assert.equal(provider.gpsStatus.value, "active");
  assert.equal(provider.arrivalPosition.value.accuracy, 12);
  provider.useSimulation();
  assert.deepEqual(fake.cleared, [17]);
  provider.dispose();
  assert.deepEqual(fake.cleared, [17]);
});

test("denied GPS returns to demonstration mode without losing its position", async () => {
  const fake = geolocationDouble();
  const simulationPosition = ref({ longitude: 120.3, latitude: 31.7, source: "simulation" });
  const provider = createLocationProvider({ simulationPosition, geolocation: fake.api });
  await provider.requestGps();
  fake.fail(1);
  assert.equal(provider.mode.value, "simulation");
  assert.equal(provider.gpsStatus.value, "denied");
  assert.equal(provider.position.value.longitude, 120.3);
  assert.deepEqual(fake.cleared, [17]);
  provider.dispose();
});
