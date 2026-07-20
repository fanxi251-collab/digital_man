<script setup>
import { ref } from "vue";
import ConversationTimeline from "./ConversationTimeline.vue";
import {
  DigitalHumanAvatarSelector,
  DigitalHumanStage,
  DigitalHumanVoiceControls,
  TranscriptConfirmation,
} from "../features/digital-human";

const props = defineProps({
  messages: { type: Array, required: true },
  isLoading: { type: Boolean, required: true },
  avatarState: { type: String, required: true },
  avatarId: { type: String, default: "mao_pro" },
  avatarReady: { type: Boolean, default: true },
  audioLevel: { type: Number, required: true },
  inputLevel: { type: Number, default: 0 },
  inputQuality: { type: String, default: "good" },
  autoGainState: { type: String, default: "unknown" },
  answerText: { type: String, default: "" },
  emotionText: { type: String, default: "" },
  microphoneState: { type: String, default: "idle" },
  transcriptConfirmation: { type: Object, default: null },
  correctionNotice: { type: String, default: "" },
});
const mode = defineModel("mode", { type: String, default: "text" });
const emit = defineEmits([
  "ask",
  "mode-change",
  "start-recording",
  "stop-recording",
  "cancel",
  "confirm-transcript",
  "avatar-change",
  "toggle-history",
]);
const question = ref("");

function setMode(nextMode) {
  emit("mode-change", nextMode);
}

function submitQuestion() {
  const value = question.value.trim();
  if (!value) return;
  emit("ask", value);
  question.value = "";
}

</script>

<template>
  <section class="chat-main" aria-label="景区 AI 导游问答">
    <header class="chat-topbar">
      <div class="chat-heading">
        <p class="brand-mark">灵境智导</p>
        <h1>景区 AI 导游</h1>
        <span>让每一次出发，都更懂灵山</span>
      </div>
      <DigitalHumanAvatarSelector
        v-if="mode === 'avatar'"
        class="topbar-avatar-selector"
        :avatar-id="avatarId"
        :avatar-ready="avatarReady"
        @avatar-change="emit('avatar-change', $event)"
      />
      <div class="topbar-actions">
        <div class="mode-switch" role="group" aria-label="交互模式">
          <button type="button" :class="{ active: mode === 'text' }" @click="setMode('text')">常规模式</button>
          <button type="button" :class="{ active: mode === 'avatar' }" @click="setMode('avatar')">数字人模式</button>
        </div>
        <button v-if="isLoading" class="ghost-button" type="button" @click="emit('cancel')">停止</button>
        <button class="history-toggle-button" type="button" aria-label="历史会话" @click="emit('toggle-history')">
          <span class="history-toggle-icon" aria-hidden="true">↺</span>
          <span>历史</span>
        </button>
      </div>
    </header>

    <ConversationTimeline
      v-if="mode === 'text'"
      :messages="messages"
      @retry="emit('ask', $event)"
      @ask="emit('ask', $event)"
    />
    <DigitalHumanStage
      v-else
      :avatar-id="avatarId"
      :state="avatarState"
      :audio-level="audioLevel"
      :answer-text="answerText"
      :emotion-text="emotionText"
    />

    <TranscriptConfirmation
      v-if="transcriptConfirmation"
      :confirmation="transcriptConfirmation"
      @confirm="emit('confirm-transcript', $event)"
    />
    <p v-if="correctionNotice" class="correction-notice">{{ correctionNotice }}</p>

    <form class="composer-card" @submit.prevent="submitQuestion">
      <label class="sr-only" for="questionInput">输入问题</label>
      <textarea
        id="questionInput"
        v-model="question"
        name="question"
        rows="2"
        placeholder="给灵境智导发送消息，例如：给我推荐灵山胜境的游玩路线"
        :disabled="mode === 'avatar' && !avatarReady"
        @keydown.enter.exact.prevent="submitQuestion"
      ></textarea>
      <div class="composer-actions">
        <template v-if="mode === 'text'">
          <div class="composer-buttons">
            <button type="submit">发送</button>
          </div>
        </template>
        <DigitalHumanVoiceControls
          v-else
          :disabled="!avatarReady"
          :microphone-state="microphoneState"
          :input-quality="inputQuality"
          :auto-gain-state="autoGainState"
          @start-recording="emit('start-recording')"
          @stop-recording="emit('stop-recording')"
        >
          <button type="submit" :disabled="!avatarReady">发送</button>
        </DigitalHumanVoiceControls>
      </div>
    </form>
  </section>
</template>
