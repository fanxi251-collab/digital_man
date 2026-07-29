<script setup>
import { computed, onMounted, ref } from "vue";
import FoodDetailDrawer from "../components/FoodDetailDrawer.vue";
import { filterFoods } from "../features/food/lib/foodFilters";
import { fetchVisitorFoods } from "../lib/visitorCatalog.js";

const foods = ref([]);
const selected = ref(null);
const loadingState = ref("正在准备灵山风味...");
const keyword = ref("");
const scope = ref("");
const category = ref("");
const taste = ref("");
const priceLevel = ref("");
const vegetarianOnly = ref(false);

const categories = computed(() => [...new Set(foods.value.map((food) => food.category).filter(Boolean))]);
const tastes = computed(() => [...new Set(foods.value.flatMap((food) => food.taste_tags || []))]);
const visibleFoods = computed(() => filterFoods(foods.value, {
  keyword: keyword.value,
  scope: scope.value,
  category: category.value,
  taste: taste.value,
  priceLevel: priceLevel.value,
  vegetarianOnly: vegetarianOnly.value,
}));
const featured = computed(() => foods.value.filter((food) => food.is_featured).slice(0, 3));

async function loadFoods() {
  loadingState.value = "正在准备灵山风味...";
  try {
    const data = await fetchVisitorFoods();
    foods.value = data.foods;
    loadingState.value = foods.value.length ? "" : "暂无已发布的美食推荐。";
  } catch (error) {
    loadingState.value = `美食加载失败：${error.message}`;
  }
}

onMounted(loadFoods);
</script>

<template>
  <main class="content-view food-view">
    <section class="food-hero">
      <div class="food-hero-copy">
        <p class="section-kicker">LINGSHAN FLAVOURS</p>
        <h1>寻味灵山，尝一席江南</h1>
        <p>从禅意蔬食到太湖鲜味，用一顿恰好的餐食为旅程留出从容。</p>
        <span>信息更新于 2026-07-19 · 营业与供应请以现场为准</span>
      </div>
      <div class="food-featured-mosaic" aria-label="编辑精选美食">
        <button v-for="(food, index) in featured" :key="food.food_id" type="button" :class="{ primary: index === 0 }" @click="selected = food">
          <img :src="food.cover_image_url || '/static/attraction-placeholder.svg'" :alt="`${food.name}菜品氛围示意`" />
          <span><small>{{ food.scope === "inside" ? "景区内" : "周边" }}</small><strong>{{ food.name }}</strong></span>
        </button>
      </div>
    </section>

    <section class="food-filter-bar" aria-label="美食筛选">
      <input v-model="keyword" type="search" placeholder="搜索地点或招牌菜" />
      <select v-model="scope"><option value="">全部范围</option><option value="inside">景区内</option><option value="nearby">周边</option></select>
      <select v-model="category"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
      <select v-model="taste"><option value="">全部口味</option><option v-for="item in tastes" :key="item">{{ item }}</option></select>
      <select v-model="priceLevel"><option value="">全部预算</option><option v-for="level in 4" :key="level" :value="String(level)">{{ "¥".repeat(level) }}</option></select>
      <label class="food-vegetarian-toggle"><input v-model="vegetarianOnly" type="checkbox" />素食友好</label>
    </section>

    <section class="food-results">
      <div class="view-section-heading"><div><p class="section-kicker">CURATED FOR YOUR JOURNEY</p><h2>今日推荐</h2></div><span>{{ visibleFoods.length }} 个结果</span></div>
      <p v-if="loadingState" class="view-notice food-notice">{{ loadingState }} <button v-if="loadingState.startsWith('美食加载失败')" type="button" @click="loadFoods">重新加载</button></p>
      <div v-else-if="visibleFoods.length" class="food-card-grid">
        <button v-for="food in visibleFoods" :key="food.food_id" class="food-card" type="button" @click="selected = food">
          <span class="food-card-image"><img loading="lazy" :src="food.cover_image_url || '/static/attraction-placeholder.svg'" :alt="`${food.name}菜品氛围示意`" /><em>{{ food.scope === "inside" ? "景区内" : "灵山周边" }}</em></span>
          <span class="food-card-body">
            <span class="food-card-meta"><small>{{ food.category }}</small><small>{{ "¥".repeat(food.price_level || 1) }}</small></span>
            <strong>{{ food.name }}</strong><span>{{ food.summary }}</span>
            <span class="food-dish-row"><i v-for="dish in food.signature_dishes.slice(0, 2)" :key="dish">{{ dish }}</i></span>
          </span>
        </button>
      </div>
      <div v-else class="food-empty-state"><span>味</span><h3>暂时没有符合条件的推荐</h3><p>试试减少一个筛选条件，或浏览全部灵山风味。</p></div>
    </section>
    <FoodDetailDrawer :food="selected" @close="selected = null" />
  </main>
</template>

