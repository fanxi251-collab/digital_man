import assert from "node:assert/strict";
import test from "node:test";

import { createRouteSimulation } from "../src/features/guided-tour/composables/useRouteSimulation.js";
import { normalizeTourRoute } from "../src/features/guided-tour/lib/tourRoute.js";

function route() {
  return normalizeTourRoute({
    route_id: "test-route",
    name: "测试路线",
    polyline: ["120.0000,31.0000", "120.0000,31.0009", "120.0010,31.0009"],
  });
}

function fakeFrames() {
  let now = 0;
  let nextId = 0;
  const callbacks = new Map();
  return {
    now: () => now,
    requestFrame(callback) {
      nextId += 1;
      callbacks.set(nextId, callback);
      return nextId;
    },
    cancelFrame(id) {
      callbacks.delete(id);
    },
    step(milliseconds) {
      now += milliseconds;
      const queued = [...callbacks.values()];
      callbacks.clear();
      queued.forEach((callback) => callback(now));
    },
    pending: () => callbacks.size,
  };
}

test("route simulation starts, pauses, resumes, changes speed, and resets", () => {
  const frames = fakeFrames();
  const simulation = createRouteSimulation({
    route: route(),
    speedMps: 10,
    ...frames,
  });

  assert.equal(simulation.status.value, "idle");
  assert.equal(simulation.position.value.source, "simulation");
  simulation.start();
  frames.step(1000);
  assert.ok(Math.abs(simulation.travelledDistance.value - 10) < 0.01);

  simulation.pause("user");
  const pausedAt = simulation.travelledDistance.value;
  frames.step(1000);
  assert.equal(simulation.travelledDistance.value, pausedAt);
  assert.equal(simulation.pauseReason.value, "user");

  simulation.setSpeed(2);
  simulation.resume();
  frames.step(1000);
  assert.ok(Math.abs(simulation.travelledDistance.value - pausedAt - 20) < 0.01);

  simulation.reset();
  assert.equal(simulation.status.value, "idle");
  assert.equal(simulation.travelledDistance.value, 0);
  assert.equal(frames.pending(), 0);
});

test("route simulation ignores a long background gap and completes at the endpoint", () => {
  const frames = fakeFrames();
  const activeRoute = route();
  const simulation = createRouteSimulation({ route: activeRoute, speedMps: 1000, ...frames });
  simulation.start();
  frames.step(5000);
  assert.equal(simulation.travelledDistance.value, 0);

  frames.step(1000);
  assert.equal(simulation.status.value, "completed");
  assert.equal(simulation.travelledDistance.value, activeRoute.totalDistance);
  assert.deepEqual(
    [simulation.position.value.longitude, simulation.position.value.latitude],
    [120.001, 31.0009],
  );
});

test("route replacement cancels the previous frame and returns to the new start", () => {
  const frames = fakeFrames();
  const simulation = createRouteSimulation({ route: route(), speedMps: 10, ...frames });
  simulation.start();
  frames.step(1000);
  const replacement = normalizeTourRoute({
    route_id: "replacement",
    polyline: ["121,32", "121.001,32"],
  });
  simulation.replaceRoute(replacement);
  assert.equal(simulation.route.value.routeId, "replacement");
  assert.equal(simulation.status.value, "idle");
  assert.deepEqual(
    [simulation.position.value.longitude, simulation.position.value.latitude],
    [121, 32],
  );
  simulation.dispose();
  assert.equal(frames.pending(), 0);
});
