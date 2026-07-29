<script setup>
import { computed, onBeforeUnmount, onMounted, watch } from "vue";
import { useRouteMap } from "../composables/useRouteMap";
import { findSuccessfulRouteSource, resolveRouteSummary } from "../lib/routeSummary.js";

const props = defineProps({
  sources: { type: Array, required: true },
});

const routeSource = computed(() => {
  return findSuccessfulRouteSource(props.sources);
});

const summary = computed(() => resolveRouteSummary(routeSource.value));
const routeMap = useRouteMap("routeMap");

watch(summary, (value) => {
  routeMap.renderRoute(value);
});

onMounted(() => routeMap.renderRoute(summary.value));
onBeforeUnmount(routeMap.destroy);
</script>

<template>
  <section class="route-panel">
    <div class="panel-heading">
      <h2>路线地图</h2>
      <span v-if="summary">
        {{ summary.mode_text || "路线" }} {{ summary.distance_text || "--" }}，预计{{ summary.duration_text || "--" }}
      </span>
    </div>
    <p v-if="summary" class="route-overview">
      从<strong>{{ summary.origin || "未确认起点" }}</strong>到<strong>{{ summary.destination || "未确认终点" }}</strong>
      · {{ summary.mode_text || "路线" }} · {{ summary.distance_text || "未知距离" }} · {{ summary.duration_text || "未知时间" }}
    </p>
    <div id="routeMap" class="route-map" aria-label="高德路线地图"></div>
    <p class="route-notice">{{ routeMap.notice.value }}</p>
    <ol class="route-steps">
      <li v-if="!summary">暂无路线数据。提问“从灵山大佛到九龙灌浴怎么走”后显示。</li>
      <li v-for="step in (summary?.steps || [])" :key="step.index || step.instruction">
        {{ step.instruction || "继续前行" }}
      </li>
    </ol>
    <p v-if="summary?.schema_version === 2" class="route-step-count">
      高德原始步骤共{{ summary.total_step_count || summary.steps?.length || 0 }}条，当前展示{{ summary.steps?.length || 0 }}条关键步骤。
    </p>
  </section>
</template>
