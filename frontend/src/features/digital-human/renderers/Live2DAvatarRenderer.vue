<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { loadLive2DLibrary } from "../lib/live2dLoader.js";
import { resolveAvatarProfile } from "../lib/live2dCharacters.js";
import {
  applyLipSyncValue,
  createExclusiveMotionController,
  createFirstFrameReveal,
  createMissingLipSyncWarning,
  initializeProfileIdleState,
  live2DMouthTarget,
  smoothLipSyncValue,
} from "../lib/live2dMotion.js";

const props = defineProps({
  avatarId: { type: String, default: "mao_pro" },
  state: { type: String, default: "idle" },
  audioLevel: { type: Number, default: 0 },
  expression: { type: String, default: null },
  motionIntent: { type: String, default: "idle" },
});
const emit = defineEmits(["ready", "error"]);
const avatarProfile = computed(() => resolveAvatarProfile(props.avatarId));

const host = ref(null);
let application = null;
let model = null;
let resizeObserver = null;
let currentMouthValue = 0;
let lifecycleToken = 0;
let lipSyncHandler = null;
let tickerHandler = null;
let firstFrameReveal = null;
let motionController = null;
const warnIfMissingLipSync = createMissingLipSyncWarning();

function fitModel() {
  if (!application || !model || !host.value) return;
  const width = Math.max(1, host.value.clientWidth);
  const height = Math.max(1, host.value.clientHeight);
  const unscaledWidth = model.width / Math.max(model.scale.x, 0.0001);
  const unscaledHeight = model.height / Math.max(model.scale.y, 0.0001);
  const fit = avatarProfile.value.fit;
  const scale = Math.min((width * 0.92) / unscaledWidth, (height * 1.06) / unscaledHeight)
    * fit.scale;
  model.scale.set(scale);
  model.position.set(width / 2, (height / 2) + (height * fit.yOffset));
  application.renderer.resize(width, height);
}

async function applyExpression(expression) {
  if (!model || !expression) return;
  try {
    await model.expression(expression);
  } catch (error) {
    // Keep the avatar usable when one optional expression fails, because speech is the primary interaction.
    console.warn(`Live2D expression ${expression} failed`, error);
  }
}

function fallbackMotionIntent() {
  return props.state === "speaking" ? "explanation" : "idle";
}

async function applySemanticMotion(intent) {
  if (!motionController) return;
  await motionController.setIntent(intent, fallbackMotionIntent());
}

function destroyRenderer() {
  lifecycleToken += 1;
  motionController?.dispose();
  motionController = null;
  firstFrameReveal?.cancel();
  firstFrameReveal = null;
  resizeObserver?.disconnect();
  resizeObserver = null;

  if (application && tickerHandler) application.ticker.remove(tickerHandler);
  if (model?.internalModel && lipSyncHandler) {
    model.internalModel.off("beforeModelUpdate", lipSyncHandler);
  }
  tickerHandler = null;
  lipSyncHandler = null;
  currentMouthValue = 0;

  if (application && model) application.stage.removeChild(model);
  model?.destroy({ children: true, texture: true, baseTexture: true });
  model = null;
  application?.destroy(true, { children: true, texture: true, baseTexture: true });
  application = null;
}

async function initializeRenderer() {
  destroyRenderer();
  const token = lifecycleToken;
  await nextTick();

  try {
    const { PIXI, Live2DModel } = await loadLive2DLibrary();
    if (token !== lifecycleToken || !host.value) return;
    Live2DModel.registerTicker(PIXI.Ticker);

    application = new PIXI.Application({
      antialias: true,
      autoDensity: true,
      backgroundAlpha: 0,
      resolution: Math.min(globalThis.devicePixelRatio || 1, 2),
    });
    host.value.appendChild(application.view);

    const loadedModel = await Live2DModel.from(avatarProfile.value.modelUrl, {
      autoInteract: false,
    });
    if (token !== lifecycleToken || !application) {
      loadedModel.destroy({ children: true, texture: true, baseTexture: true });
      return;
    }
    model = loadedModel;
    warnIfMissingLipSync(model.internalModel);
    model.anchor.set(0.5, 0.5);
    const revealGate = avatarProfile.value.idleMotion
      ? createFirstFrameReveal(model.internalModel, application.view)
      : null;
    firstFrameReveal = revealGate;
    application.stage.addChild(model);

    tickerHandler = () => {
      const target = live2DMouthTarget(props.state, props.audioLevel);
      currentMouthValue = smoothLipSyncValue(
        currentMouthValue,
        target,
        application?.ticker.deltaMS || 16.67,
      );
    };
    lipSyncHandler = () => applyLipSyncValue(model?.internalModel, currentMouthValue);
    application.ticker.add(tickerHandler);
    model.internalModel.on("beforeModelUpdate", lipSyncHandler);

    resizeObserver = new ResizeObserver(fitModel);
    resizeObserver.observe(host.value);
    fitModel();
    await initializeProfileIdleState(model, avatarProfile.value);
    if (revealGate) {
      revealGate.markMotionReady();
      const revealed = await revealGate.revealed;
      if (!revealed || token !== lifecycleToken || !model) return;
      if (firstFrameReveal === revealGate) firstFrameReveal = null;
    }
    await applyExpression(props.expression);
    if (avatarProfile.value.semanticMotions) {
      motionController = createExclusiveMotionController(model, avatarProfile.value);
      if (props.state === "idle") {
        await motionController.playEntryMotion();
      } else {
        await applySemanticMotion(props.motionIntent);
      }
    }
    emit("ready");
  } catch (error) {
    destroyRenderer();
    emit("error", error instanceof Error ? error : new Error(String(error)));
  }
}

watch(() => props.expression, (expression) => applyExpression(expression));
watch(() => props.motionIntent, (intent) => applySemanticMotion(intent));
watch(() => props.avatarId, initializeRenderer);
watch(() => props.state, (state) => {
  if (state !== "speaking") currentMouthValue = 0;
});

onMounted(initializeRenderer);
onBeforeUnmount(destroyRenderer);
</script>

<template>
  <div
    ref="host"
    class="live2d-avatar"
    role="img"
    :aria-label="`${avatarProfile.roleLabel} ${avatarProfile.label} Live2D数字人`"
  ></div>
</template>

<style scoped>
.live2d-avatar {
  position: absolute;
  inset: 34px 14px 58px;
  min-height: 280px;
  pointer-events: none;
}

.live2d-avatar :deep(canvas) {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
