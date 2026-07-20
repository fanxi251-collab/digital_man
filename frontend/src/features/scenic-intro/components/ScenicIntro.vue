<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import scenicIntroBackground from "../../../../public/images/guide-home-background.jpg";

const emit = defineEmits(["complete"]);
const root = ref(null);
const enterButton = ref(null);
const imageState = ref("loading");
const pendingMotion = ref(true);
const leaving = ref(false);

let gsapApi = null;
let animationContext = null;
let exitTimeline = null;
let completionTimer = null;
let isMounted = true;
let prefersReducedMotion = false;

function focusEntryButton() {
  nextTick(() => enterButton.value?.focus({ preventScroll: true }));
}

function finishIntro() {
  if (!isMounted) return;
  emit("complete");
}

function finishWithFallback() {
  completionTimer = window.setTimeout(finishIntro, prefersReducedMotion ? 180 : 320);
}

async function runEntrance() {
  prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (prefersReducedMotion) {
    pendingMotion.value = false;
    focusEntryButton();
    return;
  }

  try {
    const { gsap } = await import("gsap");
    if (!isMounted || !root.value) return;
    gsapApi = gsap;

    animationContext = gsap.context(() => {
      const brand = "[data-intro='brand']";
      const rule = "[data-intro='rule']";
      const title = "[data-intro='title']";
      const subtitle = "[data-intro='subtitle']";
      const action = "[data-intro='action']";

      gsap.set([brand, title, subtitle, action], { autoAlpha: 0 });
      gsap.set(rule, { scaleX: 0, transformOrigin: "left center" });
      pendingMotion.value = false;

      gsap.timeline({ defaults: { ease: "power3.out" }, onComplete: focusEntryButton })
        .fromTo("[data-intro='photo']", { filter: "blur(9px)", scale: 1.045 }, {
          filter: "blur(0px)", scale: 1, duration: 0.5,
        })
        .to(brand, { autoAlpha: 1, y: 0, duration: 0.45 }, 0.28)
        .to(rule, { scaleX: 1, duration: 0.58 }, 0.46)
        .to(title, { autoAlpha: 1, y: 0, duration: 0.58 }, 0.64)
        .to(subtitle, { autoAlpha: 1, y: 0, duration: 0.46 }, 0.9)
        .to(action, { autoAlpha: 1, y: 0, duration: 0.48 }, 1.08);
    }, root.value);
  } catch {
    // CSS remains a complete fallback so a failed optional animation chunk never blocks entry.
    pendingMotion.value = false;
    focusEntryButton();
  }
}

function enterGuide() {
  if (leaving.value) return;
  leaving.value = true;

  if (prefersReducedMotion || !gsapApi || !root.value) {
    finishWithFallback();
    return;
  }

  exitTimeline = gsapApi.timeline({ onComplete: finishIntro })
    .to("[data-intro='action']", { scale: 0.78, autoAlpha: 0, duration: 0.2, ease: "power2.in" })
    .fromTo("[data-intro='ripple']", { scale: 0.12, autoAlpha: 0.8 }, {
      scale: 18, autoAlpha: 0, duration: 0.72, ease: "power2.out",
    }, 0.08)
    .to("[data-intro='content']", { y: -18, autoAlpha: 0, duration: 0.42, ease: "power2.in" }, 0.18)
    .to(root.value, { autoAlpha: 0, duration: 0.34, ease: "sine.inOut" }, 0.48);
}

onMounted(runEntrance);

onBeforeUnmount(() => {
  isMounted = false;
  if (completionTimer) window.clearTimeout(completionTimer);
  exitTimeline?.kill();
  animationContext?.revert();
});
</script>

<template>
  <section
    ref="root"
    :class="[
      'scenic-intro',
      `is-image-${imageState}`,
      { 'is-motion-pending': pendingMotion, 'is-leaving': leaving },
    ]"
    aria-labelledby="scenicIntroTitle"
    aria-modal="true"
    role="dialog"
  >
    <img
      class="scenic-intro-photo"
      data-intro="photo"
      :src="scenicIntroBackground"
      alt=""
      draggable="false"
      @load="imageState = 'ready'"
      @error="imageState = 'error'"
    />
    <div class="scenic-intro-shade" aria-hidden="true"></div>
    <div class="scenic-intro-mist scenic-intro-mist--left" aria-hidden="true"></div>
    <div class="scenic-intro-mist scenic-intro-mist--right" aria-hidden="true"></div>
    <span class="scenic-intro-ripple" data-intro="ripple" aria-hidden="true"></span>

    <header class="scenic-intro-brand" data-intro="brand">
      <span class="scenic-intro-mark">灵</span>
      <span>灵境智导 · 灵山胜境</span>
    </header>

    <div class="scenic-intro-content" data-intro="content">
      <div class="scenic-intro-copy">
        <span class="scenic-intro-rule" data-intro="rule" aria-hidden="true"></span>
        <div class="scenic-intro-title-wrap">
          <p class="scenic-intro-kicker">MEET LINGSHAN</p>
          <h1 id="scenicIntroTitle" data-intro="title">遇见灵山，开启灵境</h1>
          <p class="scenic-intro-subtitle" data-intro="subtitle">一场风景与智慧共同展开的旅程</p>
        </div>
      </div>

      <button
        ref="enterButton"
        class="scenic-intro-enter"
        data-intro="action"
        type="button"
        @click="enterGuide"
      >
        <span>开启灵境之旅</span>
        <span class="scenic-intro-enter-icon" aria-hidden="true">→</span>
      </button>
    </div>
  </section>
</template>

<style scoped src="../scenic-intro.css"></style>
