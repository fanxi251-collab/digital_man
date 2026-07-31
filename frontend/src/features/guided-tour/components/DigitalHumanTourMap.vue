<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

import GuidedTourFallbackMap from "./GuidedTourFallbackMap.vue";
import TourMapControls from "./TourMapControls.vue";
import { createGuidedTourMap } from "../composables/useGuidedTourMap.js";

const props = defineProps({
  route: { type: Object, default: null },
  previewRoute: { type: Object, default: null },
  stops: { type: Array, default: () => [] },
  position: { type: Object, default: null },
  activeStop: { type: Object, default: null },
  dwellProgress: { type: Number, default: 0 },
  status: { type: String, default: "loading" },
  speed: { type: Number, default: 1 },
  locationMode: { type: String, default: "simulation" },
  gpsStatus: { type: String, default: "idle" },
  loadError: { type: String, default: "" },
});
const emit = defineEmits([
  "start", "pause", "resume", "speed-change", "reset", "location-mode-change",
]);
const canvas = ref(null);
const guidedMap = createGuidedTourMap(canvas);
let mounted = false;

onMounted(async () => {
  mounted = true;
  await nextTick();
  await guidedMap.initialize(props.route, props.stops);
  if (props.previewRoute) guidedMap.previewRoute(props.previewRoute);
  if (props.position) guidedMap.updatePosition(props.position);
});

watch(() => props.route, (route) => {
  if (mounted) guidedMap.renderRoute(route);
}, { deep: true });
watch(() => props.previewRoute, (route) => {
  if (!mounted) return;
  if (route) guidedMap.previewRoute(route);
  else guidedMap.clearPreview();
}, { deep: true });
watch(() => props.stops, (stops) => {
  if (mounted) guidedMap.drawStops(stops);
}, { deep: true });
watch(() => props.position, (position) => {
  if (mounted && position) guidedMap.updatePosition(position);
}, { deep: true });
watch(() => props.activeStop, (stop) => {
  if (!mounted) return;
  if (stop) guidedMap.focusStop(stop);
  else guidedMap.resumeFollow();
});

onBeforeUnmount(() => {
  mounted = false;
  guidedMap.destroy();
});
</script>

<template>
  <section class="digital-human-tour-map" aria-label="数字人实时二维地图">
    <div ref="canvas" v-show="guidedMap.mode.value !== 'fallback'" class="tour-map-canvas"></div>
    <GuidedTourFallbackMap
      v-if="guidedMap.mode.value === 'fallback'"
      :route="route"
      :preview-route="previewRoute"
      :stops="stops"
      :position="position"
      :active-stop="activeStop"
      :dwell-progress="dwellProgress"
    />
    <TourMapControls
      class="tour-map-controls-overlay"
      :status="status"
      :speed="speed"
      :location-mode="locationMode"
      :gps-status="gpsStatus"
      :disabled="status === 'error'"
      @start="emit('start')"
      @pause="emit('pause')"
      @resume="emit('resume')"
      @speed-change="emit('speed-change', $event)"
      @reset="emit('reset')"
      @location-mode-change="emit('location-mode-change', $event)"
    />
    <div class="tour-map-status" aria-live="polite">
      <strong v-if="activeStop">{{ activeStop.attraction_name }}</strong>
      <span>{{ loadError || guidedMap.notice.value }}</span>
    </div>
  </section>
</template>

<style scoped>
.digital-human-tour-map { position: relative; min-height: 270px; overflow: hidden; border: 1px solid rgba(255,255,255,.62); border-radius: 21px; background: rgba(239,249,248,.72); box-shadow: 0 18px 45px rgba(15,52,58,.14); backdrop-filter: blur(18px) saturate(120%); }
.tour-map-canvas { position: absolute; inset: 0; }
.tour-map-controls-overlay { position: absolute; z-index: 5; top: 12px; left: 12px; right: 12px; }
.tour-map-status { position: absolute; z-index: 4; right: 12px; bottom: 10px; left: 12px; display: flex; justify-content: space-between; gap: 10px; border-radius: 11px; padding: 7px 10px; background: rgba(250,253,252,.82); color: #32565b; font-size: 10px; backdrop-filter: blur(12px); }
.tour-map-status strong { color: #9a7028; white-space: nowrap; }
.tour-map-status span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
:global(.guided-tour-stop-marker) { display: block; width: 16px; height: 16px; border: 3px solid rgba(255,255,255,.95); border-radius: 50%; background: #2f7d78; box-shadow: 0 4px 14px rgba(15,52,58,.3); }
:global(.guided-tour-visitor-marker) { display: grid; place-items: center; width: 25px; height: 25px; border: 2px solid white; border-radius: 50%; background: rgba(47,125,120,.82); box-shadow: 0 0 0 7px rgba(47,125,120,.17), 0 5px 16px rgba(15,52,58,.32); }
:global(.guided-tour-visitor-marker i) { width: 8px; height: 13px; background: #fff; clip-path: polygon(50% 0,100% 100%,50% 76%,0 100%); transform: rotate(var(--tour-heading)); }
@media (max-width: 900px) { .digital-human-tour-map { min-height: 245px; } }
@media (max-width: 640px) { .digital-human-tour-map { min-height: 300px; border-radius: 17px; } .tour-map-controls-overlay { top: 8px; left: 8px; right: 8px; } }
</style>
