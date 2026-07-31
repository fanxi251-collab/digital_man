<script setup>
import { computed, nextTick, ref, watch } from "vue";
import AssistantAnswer from "../../../components/AssistantAnswer.vue";

const props = defineProps({
  answerText: { type: String, default: "" },
  state: { type: String, default: "idle" },
  contentKind: { type: String, default: "assistant" },
  answerTitle: { type: String, default: "" },
  hasRoutePreview: { type: Boolean, default: false },
  requiresManualPlay: { type: Boolean, default: false },
});
const emit = defineEmits(["accept-route", "play-narration"]);

const STICKY_THRESHOLD = 48;
const answerBody = ref(null);
const followLatest = ref(true);

const stateLabel = computed(() => ({
  idle: "待机",
  listening: "正在聆听",
  thinking: "正在思考",
  speaking: "正在讲解",
  error: "服务异常",
}[props.state] || "待机"));

const emptyCopy = computed(() => ({
  idle: "向数字人提问后，回答将在这里显示。",
  listening: "正在聆听你的问题…",
  thinking: "正在为你整理回答…",
  speaking: "正在生成回答…",
  error: "暂时无法生成回答，请稍后重试。",
}[props.state] || "向数字人提问后，回答将在这里显示。"));

const normalizedAnswer = computed(() => String(props.answerText || "").trim());
const panelTitle = computed(() => (
  props.answerTitle
  || (props.contentKind === "narration" ? "景点讲解" : "数字人回答")
));

function updateFollowState() {
  if (!answerBody.value) return;
  const { scrollHeight, scrollTop, clientHeight } = answerBody.value;
  followLatest.value = scrollHeight - scrollTop - clientHeight <= STICKY_THRESHOLD;
}

watch(() => props.answerText, async (answerText) => {
  if (!String(answerText || "").trim()) {
    followLatest.value = true;
    await nextTick();
    if (answerBody.value) answerBody.value.scrollTop = 0;
    return;
  }
  if (!followLatest.value) return;
  await nextTick();
  if (answerBody.value) answerBody.value.scrollTop = answerBody.value.scrollHeight;
});
</script>

<template>
  <aside class="digital-human-answer" aria-label="数字人最新回答">
    <header class="digital-human-answer-header">
      <strong>{{ panelTitle }}</strong>
      <span>{{ stateLabel }}</span>
    </header>
    <div
      ref="answerBody"
      :class="['digital-human-answer-body', { 'is-empty': !normalizedAnswer }]"
      @scroll="updateFollowState"
    >
      <AssistantAnswer v-if="normalizedAnswer" :answer="normalizedAnswer" />
      <p v-else>{{ emptyCopy }}</p>
    </div>
    <footer v-if="hasRoutePreview || requiresManualPlay" class="digital-human-answer-actions">
      <button v-if="requiresManualPlay" type="button" @click="emit('play-narration')">播放讲解</button>
      <button v-if="hasRoutePreview" type="button" class="route-preview-action" @click="emit('accept-route')">
        沿此路线演示
      </button>
    </footer>
  </aside>
</template>

<style scoped>
.digital-human-answer {
  width: 100%;
  min-width: 0;
  min-height: 220px;
  max-height: 360px;
  align-self: center;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.58);
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 22px 54px rgba(15, 52, 58, 0.16);
  color: var(--guide-ink, #143f46);
  backdrop-filter: blur(22px) saturate(120%);
}

.digital-human-answer-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  border-top: 1px solid rgba(20, 63, 70, 0.09);
  padding: 9px 14px 11px;
}

.digital-human-answer-actions button {
  min-height: 36px;
  border: 1px solid rgba(47, 125, 120, 0.2);
  border-radius: 999px;
  padding: 0 14px;
  background: rgba(255, 255, 255, 0.72);
  color: #2f7d78;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.digital-human-answer-actions .route-preview-action {
  border-color: transparent;
  background: #2f7d78;
  color: white;
}

.digital-human-answer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid rgba(20, 63, 70, 0.1);
  padding: 15px 18px 12px;
}

.digital-human-answer-header strong {
  font-size: 16px;
  letter-spacing: 0.02em;
}

.digital-human-answer-header span {
  border-radius: 999px;
  padding: 5px 9px;
  background: rgba(47, 125, 120, 0.1);
  color: var(--guide-accent, #2f7d78);
  font-size: 11px;
  font-weight: 800;
}

.digital-human-answer-body {
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px 20px;
  scrollbar-width: thin;
  scrollbar-color: rgba(47, 125, 120, 0.36) transparent;
}

.digital-human-answer-body > p {
  margin: 0;
  color: #274d53;
  font-size: 15px;
  line-height: 1.8;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.digital-human-answer-body :deep(.answer-text) {
  margin: 0;
  color: #274d53;
  font-size: 15px;
  line-height: 1.8;
  overflow-wrap: anywhere;
}

.digital-human-answer-body :deep(.answer-text h3) {
  margin: 14px 0 6px;
  color: var(--guide-accent, #2f7d78);
  font-size: 15px;
}

.digital-human-answer-body :deep(.answer-text h3:first-child) {
  margin-top: 0;
}

.digital-human-answer-body :deep(.answer-text p:last-child),
.digital-human-answer-body :deep(.answer-text ul:last-child) {
  margin-bottom: 0;
}

.digital-human-answer-body.is-empty {
  display: grid;
  place-items: center;
  text-align: center;
}

.digital-human-answer-body.is-empty > p {
  color: rgba(20, 63, 70, 0.58);
}

@media (max-width: 900px) {
  .digital-human-answer {
    min-height: 132px;
    max-height: 180px;
  }

  .digital-human-answer-header { padding: 10px 14px 8px; }
  .digital-human-answer-body { padding: 10px 14px 13px; }
  .digital-human-answer-actions { padding: 7px 10px 9px; }
  .digital-human-answer-body > p,
  .digital-human-answer-body :deep(.answer-text) { font-size: 14px; line-height: 1.65; }
}

@media (max-width: 640px) {
  .digital-human-answer {
    min-height: 118px;
    max-height: 150px;
    border-radius: 17px;
  }

  .digital-human-answer-header strong { font-size: 14px; }
}
</style>
