<script setup>
import { computed, nextTick } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { ScenicIntro, useGuideIntro } from "./features/scenic-intro";
import VisitorRouteTransition from "./components/VisitorRouteTransition.vue";

const route = useRoute();
const router = useRouter();
const isGuideRoute = computed(() => route.path === "/visitor/guide");
const { visible: introVisible, completeIntro } = useGuideIntro(route, router);

async function handleIntroComplete() {
  await completeIntro();
  await nextTick();
  document.querySelector("#questionInput")?.focus({ preventScroll: true });
}
</script>

<template>
  <ScenicIntro v-if="introVisible" @complete="handleIntroComplete" />
  <div
    :class="['visitor-app-shell', { 'visitor-app-shell--guide': isGuideRoute }]"
    :inert="introVisible || undefined"
    :aria-hidden="introVisible ? 'true' : undefined"
  >
    <aside class="visitor-sidebar">
      <RouterLink class="visitor-brand" to="/visitor/guide">
        <span class="visitor-brand-mark">灵</span>
        <span class="visitor-brand-copy">
          <strong>灵境智导</strong>
          <small>灵山胜境智慧游览</small>
        </span>
      </RouterLink>
      <nav class="visitor-sidebar-nav" aria-label="游客端导航">
        <RouterLink class="visitor-sidebar-link" to="/visitor/guide" aria-label="AI 智能导游">
          <svg class="visitor-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 5h16v12H8l-4 3V5Z" />
            <path d="M8 9h8M8 13h5" />
          </svg>
          <span class="visitor-nav-label"><span>AI 智能导游</span><small>导游</small></span>
        </RouterLink>
        <RouterLink class="visitor-sidebar-link" to="/visitor/explore" aria-label="景点探索">
          <svg class="visitor-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="17" cy="6" r="2" />
            <path d="m3 19 6-10 4 6 2-3 6 7H3Z" />
          </svg>
          <span class="visitor-nav-label"><span>景点探索</span><small>探索</small></span>
        </RouterLink>
        <RouterLink class="visitor-sidebar-link" to="/visitor/map" aria-label="互动地图">
          <svg class="visitor-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" />
            <path d="M9 3v15M15 6v15" />
          </svg>
          <span class="visitor-nav-label"><span>互动地图</span><small>地图</small></span>
        </RouterLink>
        <RouterLink class="visitor-sidebar-link" to="/visitor/food" aria-label="美食推荐">
          <svg class="visitor-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 10h16c0 5-3 9-8 9s-8-4-8-9Z" />
            <path d="M7 10c0-3 2-5 5-5m0 5c0-3 2-5 5-5M8 22h8" />
          </svg>
          <span class="visitor-nav-label"><span>美食推荐</span><small>美食</small></span>
        </RouterLink>
        <RouterLink class="visitor-sidebar-link" to="/visitor/feedback" aria-label="游客反馈">
          <svg class="visitor-sidebar-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M4 4h16v13H9l-5 4V4Z" />
            <path d="m12 7 1.2 2.4 2.6.4-1.9 1.8.5 2.6-2.4-1.2-2.4 1.2.5-2.6-1.9-1.8 2.6-.4L12 7Z" />
          </svg>
          <span class="visitor-nav-label"><span>游客反馈</span><small>反馈</small></span>
        </RouterLink>
      </nav>
    </aside>
    <section class="visitor-content-shell">
      <RouterView v-slot="{ Component, route }">
        <VisitorRouteTransition :component="Component" :route-key="route.path" />
      </RouterView>
    </section>
  </div>
</template>
