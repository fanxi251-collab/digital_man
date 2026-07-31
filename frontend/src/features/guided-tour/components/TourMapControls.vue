<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "loading" },
  speed: { type: Number, default: 1 },
  locationMode: { type: String, default: "simulation" },
  gpsStatus: { type: String, default: "idle" },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits([
  "start",
  "pause",
  "resume",
  "speed-change",
  "reset",
  "location-mode-change",
]);

const primaryAction = computed(() => {
  if (["loading", "narrating", "post_narration"].includes(props.status)) {
    return { label: props.status === "loading" ? "准备中" : "讲解中", event: "", disabled: true };
  }
  if (["moving", "approaching", "dwelling"].includes(props.status)) {
    return { label: "暂停", event: "pause", disabled: false };
  }
  if (props.status === "paused") return { label: "继续", event: "resume", disabled: false };
  return { label: props.status === "completed" ? "重新游览" : "开始", event: "start", disabled: false };
});

const locationLabel = computed(() => {
  if (props.locationMode === "simulation") return "演示定位";
  return ({
    requesting: "请求定位",
    active: "真实定位",
    low_accuracy: "改善精度",
    denied: "定位被拒绝",
    unavailable: "定位不可用",
  })[props.gpsStatus] || "真实定位";
});

function runPrimary() {
  if (primaryAction.value.event) emit(primaryAction.value.event);
}
</script>

<template>
  <div class="tour-map-controls" role="group" aria-label="随行导览控制">
    <button
      type="button"
      class="tour-primary-control"
      :disabled="disabled || primaryAction.disabled"
      @click="runPrimary"
    >
      <span aria-hidden="true">{{ primaryAction.event === "pause" ? "Ⅱ" : "▶" }}</span>
      {{ primaryAction.label }}
    </button>
    <div class="tour-speed-control" aria-label="演示速度">
      <button type="button" :class="{ active: speed === 1 }" @click="emit('speed-change', 1)">1×</button>
      <button type="button" :class="{ active: speed === 2 }" @click="emit('speed-change', 2)">2×</button>
    </div>
    <button type="button" class="tour-reset-control" :disabled="disabled" @click="emit('reset')">重置</button>
    <button
      type="button"
      class="tour-location-control"
      :class="{ 'is-gps': locationMode === 'gps' }"
      @click="emit('location-mode-change', locationMode === 'gps' ? 'simulation' : 'gps')"
    >
      <i aria-hidden="true"></i>{{ locationLabel }}
    </button>
  </div>
</template>

<style scoped>
.tour-map-controls {
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid rgba(255, 255, 255, 0.62);
  border-radius: 15px;
  padding: 6px;
  background: rgba(250, 253, 252, 0.82);
  box-shadow: 0 10px 28px rgba(15, 52, 58, 0.14);
  color: #143f46;
  backdrop-filter: blur(18px) saturate(125%);
}

button {
  min-height: 38px;
  border: 0;
  border-radius: 11px;
  padding: 0 11px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

button:focus-visible { outline: 2px solid #d4a64c; outline-offset: 2px; }
button:disabled { cursor: not-allowed; opacity: 0.56; }
.tour-primary-control { background: #2f7d78; color: #fff; }
.tour-primary-control span { margin-right: 4px; }
.tour-speed-control { display: flex; border-radius: 10px; background: rgba(20, 63, 70, 0.07); }
.tour-speed-control button { min-width: 38px; padding: 0 8px; }
.tour-speed-control button.active { background: rgba(255, 255, 255, 0.92); color: #2f7d78; box-shadow: 0 3px 10px rgba(20, 63, 70, 0.12); }
.tour-location-control { margin-left: auto; white-space: nowrap; }
.tour-location-control i { display: inline-block; width: 7px; height: 7px; margin-right: 6px; border-radius: 50%; background: #d4a64c; box-shadow: 0 0 0 4px rgba(212, 166, 76, 0.14); }
.tour-location-control.is-gps i { background: #2f7d78; box-shadow: 0 0 0 4px rgba(47, 125, 120, 0.14); }

@media (max-width: 640px) {
  .tour-map-controls { width: 100%; display: grid; grid-template-columns: 1fr auto auto; }
  .tour-location-control { grid-column: 1 / -1; margin-left: 0; }
  button { min-height: 44px; }
}
</style>
