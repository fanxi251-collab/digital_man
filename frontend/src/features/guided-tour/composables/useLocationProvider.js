import { computed, ref, watch } from "vue";

import { parseTourPoint } from "../lib/geo.js";

export function createLocationProvider(options = {}) {
  const simulationPosition = options.simulationPosition || ref(null);
  const geolocation = options.geolocation ?? globalThis.navigator?.geolocation ?? null;
  const maximumArrivalAccuracy = Number(options.maximumArrivalAccuracy) || 35;
  const mode = ref("simulation");
  const gpsStatus = ref("idle");
  const position = ref(normalizeSimulation(simulationPosition.value));
  const arrivalPosition = computed(() => {
    if (mode.value !== "gps") return position.value;
    return gpsStatus.value === "active" ? position.value : null;
  });
  let watchId = null;
  let disposed = false;

  const stopSimulationWatch = watch(simulationPosition, (nextPosition) => {
    if (mode.value === "simulation") position.value = normalizeSimulation(nextPosition);
  }, { deep: true, flush: "sync" });

  async function requestGps() {
    if (disposed) return false;
    if (!geolocation?.watchPosition) {
      gpsStatus.value = "unavailable";
      mode.value = "simulation";
      position.value = normalizeSimulation(simulationPosition.value);
      return false;
    }
    stopGps();
    mode.value = "gps";
    gpsStatus.value = "requesting";
    watchId = geolocation.watchPosition(
      handleGpsPosition,
      handleGpsError,
      { enableHighAccuracy: true, maximumAge: 1000, timeout: 10000 },
    );
    return true;
  }

  function handleGpsPosition(event) {
    if (disposed || mode.value !== "gps") return;
    const point = parseTourPoint(event?.coords);
    if (!point) {
      gpsStatus.value = "unavailable";
      return;
    }
    const accuracy = finiteOrNull(event.coords.accuracy);
    position.value = {
      ...point,
      accuracy,
      heading: finiteOrNull(event.coords.heading),
      speed: finiteOrNull(event.coords.speed),
      timestamp: Number(event.timestamp) || Date.now(),
      source: "gps",
    };
    gpsStatus.value = accuracy !== null && accuracy > maximumArrivalAccuracy
      ? "low_accuracy"
      : "active";
  }

  function handleGpsError(error) {
    const nextStatus = Number(error?.code) === 1 ? "denied" : "unavailable";
    stopGps();
    mode.value = "simulation";
    position.value = normalizeSimulation(simulationPosition.value);
    gpsStatus.value = nextStatus;
  }

  function useSimulation() {
    stopGps();
    mode.value = "simulation";
    gpsStatus.value = "idle";
    position.value = normalizeSimulation(simulationPosition.value);
  }

  function stopGps() {
    if (watchId === null || watchId === undefined) return;
    geolocation?.clearWatch?.(watchId);
    watchId = null;
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    stopGps();
    stopSimulationWatch();
  }

  return {
    mode,
    gpsStatus,
    position,
    arrivalPosition,
    requestGps,
    useSimulation,
    stopGps,
    dispose,
  };
}

function normalizeSimulation(value) {
  const point = parseTourPoint(value);
  if (!point) return null;
  return {
    ...point,
    accuracy: null,
    heading: finiteOrNull(value?.heading),
    speed: finiteOrNull(value?.speed),
    timestamp: Number(value?.timestamp) || Date.now(),
    source: "simulation",
  };
}

function finiteOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
