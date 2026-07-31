import { computed, ref, shallowRef, watch } from "vue";

import { createArrivalGeofence } from "./useArrivalGeofence.js";
import { createLocationProvider } from "./useLocationProvider.js";
import { createRouteSimulation } from "./useRouteSimulation.js";
import { createScenicNarration } from "./useScenicNarration.js";
import { normalizeTourRoute } from "../lib/tourRoute.js";
import { buildPublishedTourStops, stopsNearRoute } from "../lib/tourStops.js";

export function createGuidedTour(options = {}) {
  const assistantText = options.assistantText || ref("");
  const chatAvatarState = options.avatarState || ref("idle");
  const chatAudioLevel = options.chatAudioLevel || ref(0);
  const setDelay = options.setDelay || ((callback, delay) => setTimeout(callback, delay));
  const clearDelay = options.clearDelay || ((id) => clearTimeout(id));
  const catalogFetcher = options.catalogFetcher || fetchClassicTour;
  const simulation = options.simulation || createRouteSimulation(options.simulationOptions);
  const location = options.location || createLocationProvider({
    simulationPosition: simulation.position,
    ...(options.locationOptions || {}),
  });
  const geofence = options.geofence || createArrivalGeofence([]);
  const narration = options.narration || createScenicNarration(options.narrationOptions);
  const status = ref("loading");
  const loadError = ref("");
  const contentKind = ref("assistant");
  const activeStop = shallowRef(null);
  const previewRoute = shallowRef(null);
  const coreStops = shallowRef([]);
  const publishedAttractions = shallowRef([]);
  const allTourStops = shallowRef([]);
  const displayAnswer = computed(() => (
    contentKind.value === "narration" ? narration.text.value : assistantText.value
  ));
  const displayState = computed(() => (
    status.value === "narrating" ? "speaking" : chatAvatarState.value
  ));
  const displayAudioLevel = computed(() => (
    status.value === "narrating" ? narration.audioLevel.value : chatAudioLevel.value
  ));
  let loaded = false;
  let resumeTimer = null;
  let arrivalGeneration = 0;
  let disposed = false;

  const stopPositionWatch = watch(location.arrivalPosition, (position) => {
    if (disposed || simulation.status.value !== "moving" || !position) return;
    const triggered = geofence.update(position, Date.now());
    if (triggered) {
      handleArrival(triggered);
    } else if (geofence.nearestStop.value) {
      status.value = geofence.dwellProgress.value > 0 ? "dwelling" : "approaching";
    } else {
      status.value = "moving";
    }
  }, { deep: true, flush: "sync" });

  const stopSimulationWatch = watch(simulation.status, (nextStatus) => {
    if (nextStatus === "completed") status.value = "completed";
    else if (nextStatus === "moving" && !["narrating", "post_narration"].includes(status.value)) {
      status.value = "moving";
    }
  }, { flush: "sync" });

  const stopAnswerWatch = watch(assistantText, (answer) => {
    if (!String(answer || "").trim()) return;
    contentKind.value = "assistant";
  }, { flush: "sync" });

  async function load() {
    if (loaded) return true;
    status.value = "loading";
    loadError.value = "";
    try {
      const catalog = await catalogFetcher();
      const route = normalizeTourRoute(catalog);
      if (!route) throw new Error("经典路线坐标不完整");
      coreStops.value = Array.isArray(catalog.stops) ? catalog.stops : [];
      rebuildTourStops();
      simulation.replaceRoute(route);
      geofence.setStops(coreStops.value);
      loaded = true;
      status.value = "idle";
      return true;
    } catch (error) {
      loadError.value = error?.message || "经典路线加载失败";
      status.value = "error";
      return false;
    }
  }

  async function start() {
    if (!loaded && !(await load())) return false;
    await narration.prepare?.();
    contentKind.value = String(assistantText.value || "").trim() ? "assistant" : contentKind.value;
    const started = simulation.status.value === "paused"
      ? simulation.resume()
      : simulation.start();
    if (started) status.value = "moving";
    return started;
  }

  function pause(reason = "user") {
    if (simulation.status.value === "moving") simulation.pause(reason);
    status.value = "paused";
  }

  function resume() {
    if (narration.requiresManualPlay?.value) return false;
    const resumed = simulation.resume();
    if (resumed) status.value = "moving";
    return resumed;
  }

  function reset() {
    cancelResume();
    arrivalGeneration += 1;
    narration.stop?.("reset");
    simulation.reset();
    geofence.reset();
    activeStop.value = null;
    contentKind.value = String(assistantText.value || "").trim() ? "assistant" : "narration";
    status.value = "idle";
  }

  function setSpeed(multiplier) {
    simulation.setSpeed(multiplier);
  }

  async function setLocationMode(nextMode) {
    if (nextMode === "gps") await location.requestGps();
    else location.useSimulation();
  }

  function setPublishedAttractions(attractions) {
    publishedAttractions.value = Array.isArray(attractions) ? attractions : [];
    rebuildTourStops();
    if (simulation.route.value?.routeId?.startsWith("ai:")) {
      geofence.setStops(stopsNearRoute(allTourStops.value, simulation.route.value));
    }
  }

  function setAiRoutePreview(summary) {
    previewRoute.value = normalizeTourRoute(summary);
    return Boolean(previewRoute.value);
  }

  function acceptAiRoute() {
    if (!previewRoute.value) return false;
    cancelResume();
    arrivalGeneration += 1;
    narration.stop?.("route_change");
    simulation.replaceRoute(previewRoute.value);
    geofence.setStops(stopsNearRoute(allTourStops.value, previewRoute.value));
    previewRoute.value = null;
    activeStop.value = null;
    status.value = "idle";
    simulation.start();
    status.value = "moving";
    return true;
  }

  function useClassicRoute() {
    return load().then(async () => {
      const catalog = await catalogFetcher();
      const route = normalizeTourRoute(catalog);
      if (!route) return false;
      simulation.replaceRoute(route);
      geofence.setStops(coreStops.value);
      status.value = "idle";
      return true;
    });
  }

  async function handleArrival(stop) {
    const generation = ++arrivalGeneration;
    cancelResume();
    simulation.pause("arrival");
    activeStop.value = stop;
    contentKind.value = "narration";
    status.value = "narrating";
    const result = await narration.play(stop);
    if (generation !== arrivalGeneration || disposed) return;
    if (result?.status === "blocked") return;
    if (result?.status === "interrupted") return;
    scheduleResume(generation);
  }

  async function playNarrationManually() {
    const generation = arrivalGeneration;
    const result = await narration.playManually?.();
    if (generation === arrivalGeneration && result?.status === "complete") scheduleResume(generation);
    return result;
  }

  function scheduleResume(generation) {
    status.value = "post_narration";
    resumeTimer = setDelay(() => {
      resumeTimer = null;
      if (disposed || generation !== arrivalGeneration) return;
      activeStop.value = null;
      if (simulation.resume()) status.value = "moving";
    }, 1500);
  }

  function interruptForUser() {
    arrivalGeneration += 1;
    cancelResume();
    narration.stop?.("interaction");
    if (simulation.status.value === "moving") simulation.pause("interaction");
    else if (simulation.status.value === "paused") simulation.pauseReason.value = "interaction";
    activeStop.value = null;
    contentKind.value = "assistant";
    status.value = "paused";
  }

  function deactivate() {
    arrivalGeneration += 1;
    cancelResume();
    narration.stop?.("deactivate");
    if (simulation.status.value === "moving") simulation.pause("route_hidden");
    location.useSimulation();
    activeStop.value = null;
    status.value = loaded ? "paused" : status.value;
  }

  function activate() {
    if (loaded && simulation.status.value === "paused") status.value = "paused";
  }

  function rebuildTourStops() {
    allTourStops.value = buildPublishedTourStops(
      publishedAttractions.value,
      coreStops.value,
    );
  }

  function cancelResume() {
    if (resumeTimer === null) return;
    clearDelay(resumeTimer);
    resumeTimer = null;
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    arrivalGeneration += 1;
    cancelResume();
    stopPositionWatch();
    stopSimulationWatch();
    stopAnswerWatch();
    narration.dispose?.();
    location.dispose?.();
    simulation.dispose?.();
  }

  return {
    status,
    loadError,
    contentKind,
    activeStop,
    previewRoute,
    coreStops,
    allTourStops,
    stops: geofence.stops,
    route: simulation.route,
    position: location.position,
    locationMode: location.mode,
    gpsStatus: location.gpsStatus,
    speedMultiplier: simulation.speedMultiplier,
    pauseReason: simulation.pauseReason,
    dwellProgress: geofence.dwellProgress,
    displayAnswer,
    displayState,
    displayAudioLevel,
    requiresManualPlay: narration.requiresManualPlay,
    load,
    start,
    pause,
    resume,
    reset,
    setSpeed,
    setLocationMode,
    setPublishedAttractions,
    setAiRoutePreview,
    acceptAiRoute,
    useClassicRoute,
    playNarrationManually,
    interruptForUser,
    activate,
    deactivate,
    dispose,
  };
}

async function fetchClassicTour() {
  const response = await fetch("/api/visitor/guided-tour/classic");
  if (!response.ok) throw new Error(`经典路线加载失败：HTTP ${response.status}`);
  return response.json();
}
