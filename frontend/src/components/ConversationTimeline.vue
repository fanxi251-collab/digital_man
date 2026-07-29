<script setup>
import { nextTick, ref, watch } from "vue";
import AssistantAnswer from "./AssistantAnswer.vue";
import InlineRouteCard from "./InlineRouteCard.vue";

const props = defineProps({ messages: { type: Array, required: true } });
const emit = defineEmits(["retry", "ask"]);
const timeline = ref(null);
const quickPrompts = [
  "第一次来灵山胜境怎么玩？",
  "今天有哪些值得看的表演？",
  "适合老人和孩子的路线怎么走？",
  "从灵山大佛到九龙灌浴怎么走？",
];
const leftPrompts = quickPrompts.slice(0, 2);
const rightPrompts = quickPrompts.slice(2);

function askPrompt(prompt) {
  emit("ask", prompt);
}

watch(
  () => props.messages.map((message) => message.content).join("|"),
  async () => {
    await nextTick();
    if (timeline.value) timeline.value.scrollTop = timeline.value.scrollHeight;
  },
);
</script>

<template>
  <section ref="timeline" class="conversation-timeline" aria-live="polite">
    <div v-if="!messages.length" class="conversation-empty">
      <div class="quick-prompts quick-prompts--left" aria-label="左侧快捷提问">
        <button v-for="prompt in leftPrompts" :key="prompt" type="button" @click="askPrompt(prompt)">
          {{ prompt }}
        </button>
      </div>
      <div class="conversation-empty-copy">
        <p class="welcome-kicker">LINGSHAN · SMART JOURNEY</p>
        <h2>今天，想怎样遇见灵山？</h2>
        <p class="welcome-copy">从景点故事、开放时间到行程路线，我会陪你把旅途安排得从容一些。</p>
      </div>
      <div class="quick-prompts quick-prompts--right" aria-label="右侧快捷提问">
        <button v-for="prompt in rightPrompts" :key="prompt" type="button" @click="askPrompt(prompt)">
          {{ prompt }}
        </button>
      </div>
    </div>
    <article v-for="message in messages" :key="message.id" :class="['message-row', message.role]">
      <div class="message-avatar">{{ message.role === "user" ? "你" : "AI" }}</div>
      <div class="message-bubble">
        <p v-if="message.role === 'user'">{{ message.content }}</p>
        <AssistantAnswer v-else :answer="message.content" />
        <span v-if="message.pending" class="typing-indicator">正在生成…</span>
        <div v-if="message.error" class="message-error">
          {{ message.error }}
          <button
            v-if="message.retryable && message.retryQuestion"
            type="button"
            @click="emit('retry', message.retryQuestion)"
          >重试</button>
        </div>
        <InlineRouteCard v-if="message.role === 'assistant'" :sources="message.sources || []" />
      </div>
    </article>
  </section>
</template>
