import { ref, shallowRef } from "vue";

import { distanceMeters, parseTourPoint } from "../lib/geo.js";

export function createArrivalGeofence(initialStops = []) {
  const stops = shallowRef(normalizeStops(initialStops));
  const nearestStop = shallowRef(null);
  const nearestDistance = ref(Number.POSITIVE_INFINITY);
  const dwellProgress = ref(0);
  const triggeredStop = shallowRef(null);
  const triggeredIds = ref(new Set());
  let dwellingStopId = "";
  let enteredAt = null;

  function update(position, now = Date.now()) {
    triggeredStop.value = null;
    const candidates = eligibleCandidates(position);
    if (!candidates.length) {
      clearDwell();
      return null;
    }

    const candidate = candidates[0];
    nearestStop.value = candidate.stop;
    nearestDistance.value = candidate.distance;
    if (dwellingStopId !== candidate.stop.stop_id) {
      dwellingStopId = candidate.stop.stop_id;
      enteredAt = Number(now);
      dwellProgress.value = 0;
      return null;
    }

    const dwellMs = Math.max(0, Number(candidate.stop.dwell_ms) || 3000);
    const elapsed = Math.max(0, Number(now) - enteredAt);
    dwellProgress.value = dwellMs ? Math.min(1, elapsed / dwellMs) : 1;
    if (elapsed < dwellMs) return null;

    markHandled(candidate.stop.stop_id);
    triggeredStop.value = candidate.stop;
    return candidate.stop;
  }

  function eligibleCandidates(position) {
    const point = parseTourPoint(position);
    if (!point) return [];
    return stops.value
      .map((stop, index) => ({ stop, index, distance: distanceMeters(point, stop) }))
      .filter(({ stop, distance }) => {
        if (triggeredIds.value.has(stop.stop_id)) return false;
        const radius = Math.max(1, Number(stop.trigger_radius_m) || 35);
        const poorGpsAccuracy = (
          position?.source === "gps"
          && Number.isFinite(Number(position?.accuracy))
          && Number(position.accuracy) > radius
        );
        return !poorGpsAccuracy && distance <= radius;
      })
      // Route order is intentional: overlapping scenic zones should narrate in the authored sequence.
      .sort((first, second) => first.index - second.index || first.distance - second.distance);
  }

  function markHandled(stopId) {
    if (!stopId) return;
    triggeredIds.value = new Set([...triggeredIds.value, stopId]);
    dwellingStopId = "";
    enteredAt = null;
    dwellProgress.value = 1;
  }

  function setStops(nextStops) {
    stops.value = normalizeStops(nextStops);
    reset();
  }

  function reset() {
    triggeredIds.value = new Set();
    triggeredStop.value = null;
    clearDwell();
  }

  function clearDwell() {
    nearestStop.value = null;
    nearestDistance.value = Number.POSITIVE_INFINITY;
    dwellingStopId = "";
    enteredAt = null;
    dwellProgress.value = 0;
  }

  return {
    stops,
    nearestStop,
    nearestDistance,
    dwellProgress,
    triggeredStop,
    triggeredIds,
    update,
    markHandled,
    setStops,
    reset,
  };
}

function normalizeStops(stops) {
  return (stops || []).flatMap((stop) => {
    const point = parseTourPoint(stop);
    const stopId = String(stop?.stop_id || "").trim();
    return point && stopId ? [{ ...stop, ...point, stop_id: stopId }] : [];
  });
}
