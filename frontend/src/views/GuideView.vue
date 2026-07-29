<script setup>
import { onActivated, onBeforeUnmount, onDeactivated, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatMain from "../components/ChatMain.vue";
import SessionSidebar from "../components/SessionSidebar.vue";
import { useRealtimeChat } from "../composables/useRealtimeChat";
import { useSessions } from "../composables/useSessions";

const route = useRoute();
const router = useRouter();
const historyOpen = ref(false);
const sessionsApi = useSessions();
const chatApi = useRealtimeChat({
  currentSessionId: sessionsApi.currentSessionId,
  visitorId: sessionsApi.visitorId,
  onSessionChanged: sessionsApi.loadSessions,
});

async function loadSession(sessionId) {
  const messages = await sessionsApi.loadSessionMessages(sessionId);
  chatApi.restoreMessages(messages);
  historyOpen.value = false;
}

function startNewSession() {
  sessionsApi.startNewSession();
  chatApi.resetConversation("已开启新会话，请输入新的问题。");
  historyOpen.value = false;
}

async function deleteCurrentSession() {
  const deleted = await sessionsApi.deleteCurrentSession();
  if (deleted) chatApi.resetConversation("当前会话已删除，可以开始新的提问。");
}

function closeHistory() {
  historyOpen.value = false;
}

function handleHistoryKeydown(event) {
  // Escape provides a predictable keyboard exit because the drawer visually covers the guide workspace.
  if (event.key === "Escape" && historyOpen.value) closeHistory();
}

async function consumeRouteQuestion() {
  const question = String(route.query.q || "").trim();
  if (!question) return;
  // 先移除查询参数以形成一次性消费标记，避免缓存页面再次激活时重复发送付费请求。
  await router.replace({ path: "/visitor/guide" });
  await chatApi.ask(question);
}

onActivated(async () => {
  window.addEventListener("keydown", handleHistoryKeydown);
  await consumeRouteQuestion();
});

onDeactivated(() => {
  window.removeEventListener("keydown", handleHistoryKeydown);
  historyOpen.value = false;
  chatApi.suspendForRoute();
});
onBeforeUnmount(() => window.removeEventListener("keydown", handleHistoryKeydown));
</script>

<template>
  <main class="visitor-layout guide-view">
    <div class="guide-background" aria-hidden="true"></div>
    <section class="chat-area">
      <ChatMain
        v-model:mode="chatApi.mode.value"
        :messages="chatApi.messages.value"
        :is-loading="chatApi.isLoading.value"
        :avatar-state="chatApi.avatarState.value"
        :avatar-id="chatApi.avatarId.value"
        :pending-avatar-id="chatApi.pendingAvatarId.value"
        :avatar-ready="chatApi.avatarReady.value"
        :audio-level="chatApi.audioLevel.value"
        :input-level="chatApi.inputLevel.value"
        :input-quality="chatApi.inputQuality.value"
        :auto-gain-state="chatApi.autoGainState.value"
        :answer-text="chatApi.assistantTranscript.value"
        :emotion-text="chatApi.assistantTranscript.value"
        :microphone-state="chatApi.microphoneState.value"
        :transcript-confirmation="chatApi.transcriptConfirmation.value"
        :correction-notice="chatApi.correctionNotice.value"
        @ask="chatApi.ask"
        @mode-change="chatApi.setMode"
        @start-recording="chatApi.startRecording"
        @stop-recording="chatApi.stopRecording"
        @cancel="chatApi.cancelResponse"
        @confirm-transcript="chatApi.confirmTranscript"
        @avatar-change="chatApi.setAvatar"
        @toggle-history="historyOpen = true"
      />
    </section>
    <Transition name="history-drawer">
      <div v-if="historyOpen" class="history-drawer-backdrop" @click.self="closeHistory">
        <aside class="history-drawer" aria-label="历史会话" aria-modal="true" role="dialog">
          <button class="history-drawer-close" type="button" aria-label="关闭历史会话" @click="closeHistory">×</button>
          <SessionSidebar
            :sessions="sessionsApi.sessions.value"
            :current-session-id="sessionsApi.currentSessionId.value"
            :status="sessionsApi.status.value"
            @new-session="startNewSession"
            @load-session="loadSession"
            @delete-current-session="deleteCurrentSession"
          />
        </aside>
      </div>
    </Transition>
  </main>
</template>
