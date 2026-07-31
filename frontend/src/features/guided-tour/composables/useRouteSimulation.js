import { computed, ref, shallowRef } from "vue";

import { interpolateRoutePosition } from "../lib/geo.js";

const MAX_ACTIVE_FRAME_GAP_MS = 2000;

export function createRouteSimulation(options = {}) {
  const now = options.now || (() => performance.now());
  const requestFrame = options.requestFrame || ((callback) => requestAnimationFrame(callback));
  const cancelFrame = options.cancelFrame || ((id) => cancelAnimationFrame(id));
  const speedMps = Math.max(0.1, Number(options.speedMps) || 8);
  const route = shallowRef(options.route || null);
  const status = ref("idle");
  const pauseReason = ref("");
  const speedMultiplier = ref(1);
  const travelledDistance = ref(0);
  const position = ref(positionAt(0));
  const progress = computed(() => (
    route.value?.totalDistance
      ? Math.min(1, travelledDistance.value / route.value.totalDistance)
      : 0
  ));
  let frameId = null;
  let previousTimestamp = 0;
  let disposed = false;

  function start() {
    if (disposed || !route.value || status.value === "moving") return false;
    if (status.value === "completed") reset();
    status.value = "moving";
    pauseReason.value = "";
    previousTimestamp = now();
    scheduleFrame();
    return true;
  }

  function pause(reason = "user") {
    if (status.value !== "moving") return;
    cancelScheduledFrame();
    status.value = "paused";
    pauseReason.value = reason;
  }

  function resume() {
    if (status.value !== "paused") return false;
    status.value = "moving";
    pauseReason.value = "";
    previousTimestamp = now();
    scheduleFrame();
    return true;
  }

  function setSpeed(multiplier) {
    const normalized = Number(multiplier);
    if (![1, 2].includes(normalized)) return false;
    speedMultiplier.value = normalized;
    return true;
  }

  function reset() {
    cancelScheduledFrame();
    travelledDistance.value = 0;
    status.value = "idle";
    pauseReason.value = "";
    position.value = positionAt(0);
  }

  function replaceRoute(nextRoute) {
    cancelScheduledFrame();
    route.value = nextRoute || null;
    travelledDistance.value = 0;
    status.value = "idle";
    pauseReason.value = "";
    position.value = positionAt(0);
  }

  function tick(timestamp) {
    frameId = null;
    if (disposed || status.value !== "moving" || !route.value) return;
    const deltaMs = Math.max(0, Number(timestamp) - previousTimestamp);
    previousTimestamp = Number(timestamp);
    // Ignoring long background gaps prevents a restored tab from jumping across several arrival zones.
    if (deltaMs <= MAX_ACTIVE_FRAME_GAP_MS) {
      travelledDistance.value = Math.min(
        route.value.totalDistance,
        travelledDistance.value + speedMps * speedMultiplier.value * deltaMs / 1000,
      );
      position.value = positionAt(travelledDistance.value, timestamp);
    }
    if (travelledDistance.value >= route.value.totalDistance) {
      status.value = "completed";
      pauseReason.value = "";
      return;
    }
    scheduleFrame();
  }

  function scheduleFrame() {
    if (frameId === null && !disposed && status.value === "moving") {
      frameId = requestFrame(tick);
    }
  }

  function cancelScheduledFrame() {
    if (frameId === null) return;
    cancelFrame(frameId);
    frameId = null;
  }

  function positionAt(distance, timestamp = now()) {
    const point = route.value
      ? interpolateRoutePosition(route.value, distance)
      : null;
    return point ? {
      ...point,
      accuracy: null,
      speed: speedMps * speedMultiplier.value,
      timestamp: Number(timestamp) || 0,
      source: "simulation",
    } : null;
  }

  function dispose() {
    disposed = true;
    cancelScheduledFrame();
    status.value = "idle";
  }

  return {
    route,
    status,
    pauseReason,
    speedMultiplier,
    travelledDistance,
    position,
    progress,
    start,
    pause,
    resume,
    setSpeed,
    reset,
    replaceRoute,
    dispose,
  };
}
