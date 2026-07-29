<script setup>
import { computed, nextTick, onActivated, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import AttractionDetailDrawer from "../components/AttractionDetailDrawer.vue";
import FoodDetailDrawer from "../components/FoodDetailDrawer.vue";
import { useInteractiveMap } from "../composables/useInteractiveMap";
import { normalizeAttractionPlace, normalizeFoodPlace } from "../lib/mapPlaces";
import { fetchVisitorAttractions, fetchVisitorFoods } from "../lib/visitorCatalog.js";

const route = useRoute();
const places = ref([]);
const selected = ref(null);
const drawerAttraction = ref(null);
const drawerFood = ref(null);
const activeLayer = ref("all");
const originId = ref("");
const destinationId = ref("");
const routeMode = ref("walking");
const routeSummary = ref(null);
const routeStatus = ref("请选择起点和终点。 ");
const loadStatus = ref("正在加载景点与美食地点...");
const interactiveMap = useInteractiveMap("interactiveMap");
let hasLoaded = false;

const visiblePlaces = computed(() => places.value.filter((place) => (
  activeLayer.value === "all" || place.kind === activeLayer.value
)));
const attractionCount = computed(() => places.value.filter((place) => place.kind === "attraction").length);
const foodCount = computed(() => places.value.filter((place) => place.kind === "food").length);

async function loadPlaces() {
  if (hasLoaded) return;
  loadStatus.value = "正在加载景点与美食地点...";
  try {
    const [attractionResult, foodResult] = await Promise.allSettled([
      fetchVisitorAttractions(),
      fetchVisitorFoods(),
    ]);
    const attractions = attractionResult.status === "fulfilled" ? attractionResult.value.attractions : [];
    const foods = foodResult.status === "fulfilled" ? foodResult.value.foods : [];
    if (attractionResult.status === "rejected" && foodResult.status === "rejected") {
      throw attractionResult.reason || foodResult.reason || new Error("地点加载失败");
    }
    places.value = [
      ...attractions.map(normalizeAttractionPlace),
      ...foods.map(normalizeFoodPlace),
    ];
    hasLoaded = true;
    loadStatus.value = places.value.length ? "" : "暂无可显示的地点。";
    await nextTick();
    await interactiveMap.initialize(visiblePlaces.value, selectPlace);
    applyRouteQuery();
    if (!selected.value && places.value[0]) selectPlace(places.value[0]);
  } catch (error) {
    loadStatus.value = `地点加载失败：${error.message}`;
  }
}

function applyRouteQuery() {
  const requestedFood = String(route.query.food || "");
  const requestedAttraction = String(route.query.attraction || "");
  const target = places.value.find((place) => (
    (place.kind === "food" && place.source_id === requestedFood)
    || (place.kind === "attraction" && place.source_id === requestedAttraction)
  ));
  if (!target) return;
  activeLayer.value = target.kind;
  selectPlace(target);
}

function selectPlace(place) {
  selected.value = place;
  destinationId.value ||= place.place_id;
  interactiveMap.selectPlace(place);
}

function showDetails() {
  if (selected.value?.kind === "food") drawerFood.value = selected.value.source;
  else drawerAttraction.value = selected.value?.source || null;
}

async function planRoute() {
  if (!originId.value || !destinationId.value) return void (routeStatus.value = "请选择起点和终点。 ");
  if (originId.value === destinationId.value) return void (routeStatus.value = "起点和终点不能相同。 ");
  const origin = places.value.find((place) => place.place_id === originId.value);
  const destination = places.value.find((place) => place.place_id === destinationId.value);
  if (!origin || !destination) return void (routeStatus.value = "所选地点已不可用，请重新选择。 ");
  const params = new URLSearchParams({
    origin: origin.name,
    destination: destination.name,
    origin_location: `${origin.longitude},${origin.latitude}`,
    destination_location: `${destination.longitude},${destination.latitude}`,
    mode: routeMode.value,
  });
  routeStatus.value = "正在规划路线...";
  try {
    const response = await fetch(`/api/tools/map/route?${params}`);
    const data = await response.json();
    if (!response.ok || data.status !== "ok") throw new Error(data.message || `HTTP ${response.status}`);
    routeSummary.value = data.data?.route_summary || data.data || null;
    interactiveMap.renderRoute(routeSummary.value);
    routeStatus.value = `${routeSummary.value?.mode_text || "路线"} ${routeSummary.value?.distance_text || ""}，预计 ${routeSummary.value?.duration_text || "--"}`;
  } catch (error) {
    routeStatus.value = `路线规划失败：${error.message}`;
  }
}

watch(activeLayer, async () => {
  await nextTick();
  interactiveMap.setPlaces(visiblePlaces.value);
  if (selected.value && !visiblePlaces.value.includes(selected.value)) {
    selected.value = visiblePlaces.value[0] || null;
  }
});
watch(selected, (place) => interactiveMap.selectPlace(place));
watch(() => [route.query.food, route.query.attraction], applyRouteQuery);
onMounted(loadPlaces);
onActivated(async () => {
  await nextTick();
  interactiveMap.resize();
  applyRouteQuery();
});
</script>

<template>
  <main class="content-view map-view">
    <section class="map-intro">
      <div><p class="section-kicker">INTERACTIVE MAP</p><h1>互动地图</h1><p>在景点与风味之间自由组合，规划景区内外的步行或驾车路线。</p></div>
      <span>{{ attractionCount }} 个景点 · {{ foodCount }} 处美食</span>
    </section>
    <section class="interactive-map-layout">
      <aside class="map-sidebar">
        <div class="map-layer-switch" aria-label="地图图层">
          <button v-for="layer in [['all', '全部'], ['attraction', '景点'], ['food', '美食']]" :key="layer[0]" type="button" :class="{ active: activeLayer === layer[0] }" @click="activeLayer = layer[0]">{{ layer[1] }}</button>
        </div>
        <div class="route-planner">
          <h2>路线规划</h2>
          <label>起点<select v-model="originId"><option value="">请选择</option><option v-for="place in places" :key="place.place_id" :value="place.place_id">{{ place.kind === "food" ? "美食 · " : "景点 · " }}{{ place.name }}</option></select></label>
          <label>终点<select v-model="destinationId"><option value="">请选择</option><option v-for="place in places" :key="place.place_id" :value="place.place_id">{{ place.kind === "food" ? "美食 · " : "景点 · " }}{{ place.name }}</option></select></label>
          <div class="route-mode-switch"><button type="button" :class="{ active: routeMode === 'walking' }" @click="routeMode = 'walking'">步行</button><button type="button" :class="{ active: routeMode === 'driving' }" @click="routeMode = 'driving'">驾车</button></div>
          <button class="primary-button" type="button" @click="planRoute">开始规划</button>
          <p class="view-notice">{{ routeStatus }}</p>
        </div>
        <p v-if="loadStatus" class="view-notice">{{ loadStatus }}</p>
        <div v-else class="map-attraction-list">
          <button v-for="place in visiblePlaces" :key="place.place_id" type="button" :class="{ active: selected?.place_id === place.place_id, 'is-food': place.kind === 'food' }" @click="selectPlace(place)">
            <img :src="place.source.cover_image_url || '/static/attraction-placeholder.svg'" :alt="place.name" />
            <span><strong>{{ place.name }}</strong><small>{{ place.kind === "food" ? `美食 · ${place.source.category}` : `${place.source.category} · ${place.source.suggested_duration_minutes} 分钟` }}</small></span>
          </button>
        </div>
      </aside>
      <section class="map-canvas-panel">
        <div id="interactiveMap" class="interactive-map-canvas" aria-label="灵山胜境景点与美食互动地图"></div>
        <p class="map-notice">{{ interactiveMap.notice.value }}</p>
        <article v-if="selected" class="map-selected-card" :class="{ 'is-food': selected.kind === 'food' }">
          <img :src="selected.source.cover_image_url || '/static/attraction-placeholder.svg'" :alt="selected.name" />
          <div><small>{{ selected.kind === "food" ? `美食 · ${selected.source.category}` : selected.source.category }}</small><h2>{{ selected.name }}</h2><p>{{ selected.summary }}</p><button type="button" @click="showDetails">查看详情</button></div>
        </article>
        <ol v-if="routeSummary?.steps?.length" class="map-route-steps"><li v-for="step in routeSummary.steps" :key="step.index || step.instruction">{{ step.instruction }}</li></ol>
        <p v-if="routeSummary?.schema_version === 2" class="route-step-count">高德原始步骤共{{ routeSummary.total_step_count || routeSummary.steps?.length || 0 }}条，当前展示{{ routeSummary.steps?.length || 0 }}条关键步骤。</p>
      </section>
    </section>
    <AttractionDetailDrawer :attraction="drawerAttraction" @close="drawerAttraction = null" />
    <FoodDetailDrawer :food="drawerFood" @close="drawerFood = null" />
  </main>
</template>
