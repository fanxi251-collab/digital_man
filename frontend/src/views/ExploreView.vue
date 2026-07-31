
<script setup>
import { computed, onMounted, ref } from "vue";
import AttractionDetailDrawer from "../components/AttractionDetailDrawer.vue";
import { filterAttractions } from "../features/explore/lib/attractionFilters.js";
import { fetchVisitorAttractions } from "../lib/visitorCatalog.js";

const attractions = ref([]);
const selected = ref(null);
const keyword = ref("");
const category = ref("");
const loadingState = ref("正在加载景点...");

const categories = computed(() => [...new Set(attractions.value.map((item) => item.category).filter(Boolean))]);
const visibleAttractions = computed(() => filterAttractions(attractions.value, {
  keyword: keyword.value,
  category: category.value,
}));
const featured = computed(() => visibleAttractions.value.filter((item) => item.is_featured));

async function loadAttractions() {
  try {
    const data = await fetchVisitorAttractions();
    attractions.value = data.attractions;
    loadingState.value = attractions.value.length ? "" : "暂无已发布景点。";
  } catch (error) {
    loadingState.value = `景点加载失败：${error.message}`;
  }
}

onMounted(loadAttractions);
</script>

<template>
  <main class="content-view explore-view">
    <section class="explore-hero">
      <div>
        <p class="section-kicker">LINGSHAN DISCOVERY</p>
        <h1>在山水与人文之间，遇见灵山</h1>
        <p>从庄严地标到沉浸式文化体验，用图文发现值得停留的每一处景观。</p>
      </div>
      <div class="explore-stat"><strong>{{ attractions.length }}</strong><span>个精选景点</span></div>
    </section>

    <section class="explore-toolbar" aria-label="景点筛选">
      <input v-model="keyword" type="search" placeholder="搜索景点、特色或标签" />
      <select v-model="category"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
    </section>

    <section v-if="featured.length" class="featured-section">
      <div class="view-section-heading"><div><p class="section-kicker">EDITOR'S PICK</p><h2>推荐景点</h2></div><span>第一次到访不容错过</span></div>
      <div class="attraction-grid featured-grid">
        <button v-for="item in featured" :key="item.attraction_id" class="attraction-card" type="button" @click="selected = item">
          <img :src="item.cover_image_url || '/static/attraction-placeholder.svg'" :alt="item.name" />
          <span class="card-body"><small>{{ item.category }}</small><strong>{{ item.name }}</strong><span>{{ item.summary }}</span><em>{{ item.suggested_duration_minutes }} 分钟 · {{ item.opening_hours }}</em></span>
        </button>
      </div>
    </section>

    <section class="all-attractions-section">
      <div class="view-section-heading"><div><p class="section-kicker">ALL SIGHTS</p><h2>全部景点</h2></div><span>{{ visibleAttractions.length }} 个结果</span></div>
      <p v-if="loadingState" class="view-notice">{{ loadingState }}</p>
      <div class="attraction-grid">
        <button v-for="item in visibleAttractions" :key="item.attraction_id" class="attraction-card" type="button" @click="selected = item">
          <img :src="item.cover_image_url || '/static/attraction-placeholder.svg'" :alt="item.name" />
          <span class="card-body"><small>{{ item.category }}</small><strong>{{ item.name }}</strong><span>{{ item.summary }}</span><em>{{ item.suggested_duration_minutes }} 分钟 · {{ item.opening_hours }}</em></span>
        </button>
      </div>
    </section>
    <AttractionDetailDrawer :attraction="selected" @close="selected = null" />
  </main>
</template>
