<script setup>
import { KeepAlive, nextTick } from "vue";

defineProps({
  component: { type: [Object, Function], required: true },
  routeKey: { type: String, required: true },
});

async function focusEnteredPage(element) {
  await nextTick();
  const main = element?.matches?.("main") ? element : element?.querySelector?.("main");
  if (!main) return;
  main.setAttribute("tabindex", "-1");
  main.focus({ preventScroll: true });
}
</script>

<template>
  <div class="visitor-route-stage">
    <Transition
      name="center-fade"
      mode="out-in"
      @after-enter="focusEnteredPage"
    >
      <KeepAlive :max="5">
        <component :is="component" :key="routeKey" />
      </KeepAlive>
    </Transition>
  </div>
</template>
