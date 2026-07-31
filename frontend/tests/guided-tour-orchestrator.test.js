import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, ref, shallowRef } from "vue";

import { createGuidedTour } from "../src/features/guided-tour/composables/useGuidedTour.js";

function dependencies() {
  const route = {
    routeId: "classic",
    name: "经典路线",
    points: [{ longitude: 120, latitude: 31 }, { longitude: 120.01, latitude: 31 }],
    totalDistance: 1000,
  };
  const stop = {
    stop_id: "one",
    attraction_name: "测试景点",
    longitude: 120,
    latitude: 31,
    narration_text: "测试讲解",
  };
  const simulation = {
    route: shallowRef(route),
    status: ref("idle"),
    position: ref({ longitude: 120, latitude: 31, source: "simulation" }),
    speedMultiplier: ref(1),
    pauseReason: ref(""),
    replaceRoute(next) { this.route.value = next; this.status.value = "idle"; },
    start() { this.status.value = "moving"; return true; },
    pause(reason) { this.status.value = "paused"; this.pauseReason.value = reason; },
    resume() { this.status.value = "moving"; return true; },
    reset() { this.status.value = "idle"; },
    setSpeed(value) { this.speedMultiplier.value = value; },
    dispose() {},
  };
  const location = {
    mode: ref("simulation"),
    gpsStatus: ref("idle"),
    position: simulation.position,
    arrivalPosition: simulation.position,
    async requestGps() { this.mode.value = "gps"; },
    useSimulation() { this.mode.value = "simulation"; },
    dispose() {},
  };
  let shouldTrigger = false;
  const geofence = {
    stops: shallowRef([stop]),
    nearestStop: shallowRef(null),
    dwellProgress: ref(0),
    triggeredIds: ref(new Set()),
    update() {
      if (!shouldTrigger) return null;
      shouldTrigger = false;
      return stop;
    },
    setStops(value) { this.stops.value = value; },
    reset() { this.triggeredIds.value = new Set(); },
  };
  let finishNarration;
  const narration = {
    text: ref(""),
    title: ref(""),
    state: ref("idle"),
    audioLevel: ref(0.5),
    requiresManualPlay: ref(false),
    async prepare() {},
    play(nextStop) {
      this.text.value = nextStop.narration_text;
      this.state.value = "playing";
      return new Promise((resolve) => { finishNarration = resolve; });
    },
    stop() { this.state.value = "idle"; finishNarration?.({ status: "interrupted" }); },
    dispose() {},
  };
  let delayedCallback;
  return {
    route,
    stop,
    simulation,
    location,
    geofence,
    narration,
    trigger() { shouldTrigger = true; simulation.position.value = { ...simulation.position.value }; },
    finish() { narration.state.value = "complete"; finishNarration({ status: "complete" }); },
    runDelay() { delayedCallback?.(); },
    options: {
      simulation,
      location,
      geofence,
      narration,
      catalogFetcher: async () => ({
        route_id: "classic",
        name: "经典路线",
        default_speed_mps: 8,
        polyline: ["120,31", "120.01,31"],
        stops: [stop],
      }),
      setDelay(callback) { delayedCallback = callback; return 1; },
      clearDelay() { delayedCallback = null; },
    },
  };
}

test("arrival pauses movement, narrates, waits, and resumes automatically", async () => {
  const deps = dependencies();
  const tour = createGuidedTour(deps.options);
  await tour.load();
  await tour.start();
  deps.trigger();
  await nextTick();
  assert.equal(deps.simulation.status.value, "paused");
  assert.equal(tour.status.value, "narrating");
  assert.equal(tour.displayAnswer.value, "测试讲解");
  deps.finish();
  await nextTick();
  assert.equal(tour.status.value, "post_narration");
  deps.runDelay();
  assert.equal(deps.simulation.status.value, "moving");
  assert.equal(tour.status.value, "moving");
  tour.dispose();
});

test("user interaction interrupts narration and keeps the tour paused", async () => {
  const deps = dependencies();
  const assistantText = ref("");
  const tour = createGuidedTour({ ...deps.options, assistantText });
  await tour.load();
  await tour.start();
  deps.trigger();
  await nextTick();
  tour.interruptForUser();
  assistantText.value = "新的 AI 回答";
  await nextTick();
  assert.equal(deps.simulation.status.value, "paused");
  assert.equal(deps.simulation.pauseReason.value, "interaction");
  assert.equal(tour.displayAnswer.value, "新的 AI 回答");
  assert.equal(tour.contentKind.value, "assistant");
  tour.dispose();
});
