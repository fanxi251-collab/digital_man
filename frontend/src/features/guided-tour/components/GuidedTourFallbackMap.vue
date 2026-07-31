<script setup>
import { computed } from "vue";

import {
  buildProjectionBounds,
  projectTourPoint,
  projectTourPolyline,
} from "../lib/fallbackProjection.js";

const props = defineProps({
  route: { type: Object, default: null },
  previewRoute: { type: Object, default: null },
  stops: { type: Array, default: () => [] },
  position: { type: Object, default: null },
  activeStop: { type: Object, default: null },
  dwellProgress: { type: Number, default: 0 },
});

const allPoints = computed(() => [
  ...(props.route?.points || []),
  ...(props.previewRoute?.points || []),
  ...props.stops,
  ...(props.position ? [props.position] : []),
]);
const bounds = computed(() => buildProjectionBounds(allPoints.value));
const routePoints = computed(() => projectTourPolyline(props.route?.points || [], bounds.value));
const previewPoints = computed(() => projectTourPolyline(props.previewRoute?.points || [], bounds.value));
const projectedStops = computed(() => props.stops.flatMap((stop) => {
  const point = projectTourPoint(stop, bounds.value);
  return point ? [{ stop, ...point }] : [];
}));
const visitor = computed(() => projectTourPoint(props.position, bounds.value));
</script>

<template>
  <div class="guided-tour-fallback" aria-label="本地景区导览图">
    <div class="guided-tour-fallback-shade"></div>
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <polyline v-if="previewPoints" :points="previewPoints" class="fallback-preview-route" />
      <polyline v-if="routePoints" :points="routePoints" class="fallback-current-route" />
    </svg>
    <span
      v-for="item in projectedStops"
      :key="item.stop.stop_id"
      class="fallback-stop"
      :class="{ active: activeStop?.stop_id === item.stop.stop_id }"
      :style="{ left: `${item.x}%`, top: `${item.y}%` }"
      :title="item.stop.attraction_name"
    >
      <i :style="{ '--dwell-progress': `${Math.max(0, Math.min(1, dwellProgress)) * 360}deg` }"></i>
      <small>{{ item.stop.attraction_name }}</small>
    </span>
    <span
      v-if="visitor"
      class="fallback-visitor"
      :style="{
        left: `${visitor.x}%`,
        top: `${visitor.y}%`,
        '--tour-heading': `${Number(position?.heading) || 0}deg`,
      }"
      aria-label="游客当前位置"
    ><i></i></span>
    <p>本地导览图 · 路线与位置演示正常运行</p>
  </div>
</template>

<style scoped>
.guided-tour-fallback { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; background: #7bb6c1 url('/images/guide-home-background.jpg') center 52% / cover no-repeat; }
.guided-tour-fallback-shade { position: absolute; inset: 0; background: linear-gradient(155deg, rgba(224, 244, 243, .3), rgba(16, 73, 76, .32)); backdrop-filter: blur(1.5px) saturate(80%); }
svg { position: absolute; inset: 8% 4% 11%; width: 92%; height: 81%; overflow: visible; }
polyline { fill: none; vector-effect: non-scaling-stroke; stroke-linecap: round; stroke-linejoin: round; }
.fallback-current-route { stroke: #2f7d78; stroke-width: 3.1; filter: drop-shadow(0 2px 3px rgba(255,255,255,.8)); }
.fallback-preview-route { stroke: #d4a64c; stroke-width: 2.4; stroke-dasharray: 5 4; }
.fallback-stop, .fallback-visitor { position: absolute; z-index: 2; transform: translate(-50%, -50%); }
.fallback-stop > i { display: block; width: 14px; height: 14px; border: 3px solid rgba(255,255,255,.92); border-radius: 50%; background: #2f7d78; box-shadow: 0 3px 12px rgba(15,52,58,.32); }
.fallback-stop small { position: absolute; top: 18px; left: 50%; transform: translateX(-50%); white-space: nowrap; border-radius: 7px; padding: 2px 5px; background: rgba(255,255,255,.82); color: #143f46; font-size: 9px; font-weight: 800; }
.fallback-stop.active > i { width: 18px; height: 18px; background: conic-gradient(#d4a64c var(--dwell-progress), rgba(255,255,255,.76) 0); }
.fallback-visitor { width: 24px; height: 24px; border: 2px solid rgba(255,255,255,.92); border-radius: 50%; background: rgba(47,125,120,.2); box-shadow: 0 0 0 7px rgba(47,125,120,.15), 0 5px 16px rgba(15,52,58,.35); }
.fallback-visitor i { position: absolute; left: 8px; top: 4px; width: 7px; height: 12px; border-radius: 7px 7px 3px 3px; background: #fff; clip-path: polygon(50% 0, 100% 100%, 50% 76%, 0 100%); transform: rotate(var(--tour-heading)); }
.guided-tour-fallback > p { position: absolute; right: 12px; bottom: 9px; margin: 0; color: rgba(255,255,255,.92); font-size: 10px; font-weight: 700; text-shadow: 0 1px 5px rgba(0,0,0,.35); }
@media (prefers-reduced-motion: reduce) { .fallback-stop, .fallback-visitor { transition: none; } }
</style>
