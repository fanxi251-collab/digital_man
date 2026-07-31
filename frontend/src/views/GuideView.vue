<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ChatMain from "../components/ChatMain.vue";
import SessionSidebar from "../components/SessionSidebar.vue";
import { useRealtimeChat } from "../composables/useRealtimeChat";
import { useSessions } from "../composables/useSessions";
import { createGuidedTour } from "../features/digital-human";
import { fetchVisitorAttractions } from "../lib/visitorCatalog.js";

const route = useRoute();
const router = useRouter();
const historyOpen = ref(false);
const sessionsApi = useSessions();
const chatApi = useRealtimeChat({
  currentSessionId: sessionsApi.currentSessionId,
  visitorId: sessionsApi.visitorId,
  onSessionChanged: sessionsApi.loadSessions,
});
const guidedTour = createGuidedTour({
  assistantText: chatApi.assistantTranscript,
  avatarState: chatApi.avatarState,
  chatAudioLevel: chatApi.audioLevel,
});
const tourAnswerTitle = computed(() => (
  guidedTour.contentKind.value === "narration"
    ? guidedTour.activeStop.value?.attraction_name || "景点讲解"
    : "数字人回答"
));
let attractionsLoaded = false;

async function ensureGuidedTourData() {
  await guidedTour.load();
  if (attractionsLoaded) return;
  try {
    const result = await fetchVisitorAttractions();
    guidedTour.setPublishedAttractions(result.attractions || []);
    attractionsLoaded = true;
  } catch {
    // The approved six-stop route remains usable when the optional public catalog request fails.
  }
}

async function handleAsk(question) {
  guidedTour.interruptForUser();
  return chatApi.ask(question);
}

async function handleStartRecording() {
  guidedTour.interruptForUser();
  return chatApi.startRecording();
}

async function handleModeChange(nextMode) {
  chatApi.setMode(nextMode);
  if (nextMode === "avatar") {
    guidedTour.activate();
    await ensureGuidedTourData();
  } else {
    guidedTour.deactivate();
  }
}

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
  await handleAsk(question);
}

watch(chatApi.latestRouteSummary, (summary) => {
  guidedTour.setAiRoutePreview(summary);
}, { deep: true });

onActivated(async () => {
  window.addEventListener("keydown", handleHistoryKeydown);
  guidedTour.activate();
  if (chatApi.mode.value === "avatar") await ensureGuidedTourData();
  await consumeRouteQuestion();
});

onDeactivated(() => {
  window.removeEventListener("keydown", handleHistoryKeydown);
  historyOpen.value = false;
  guidedTour.deactivate();
  chatApi.suspendForRoute();
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleHistoryKeydown);
  guidedTour.dispose();
});
</script>

<template>
  <main class="visitor-layout guide-view">
    <div class="guide-background" aria-hidden="true"></div>
    <section class="chat-area">
      <ChatMain
        v-model:mode="chatApi.mode.value"
        :messages="chatApi.messages.value"
        :is-loading="chatApi.isLoading.value"
        :avatar-state="guidedTour.displayState.value"
        :avatar-id="chatApi.avatarId.value"
        :pending-avatar-id="chatApi.pendingAvatarId.value"
        :avatar-ready="chatApi.avatarReady.value"
        :audio-level="guidedTour.displayAudioLevel.value"
        :input-level="chatApi.inputLevel.value"
        :input-quality="chatApi.inputQuality.value"
        :auto-gain-state="chatApi.autoGainState.value"
        :answer-text="guidedTour.displayAnswer.value"
        :emotion-text="guidedTour.displayAnswer.value"
        :latest-user-text="chatApi.latestUserText.value"
        :has-route-source="chatApi.hasRouteSource.value"
        :microphone-state="chatApi.microphoneState.value"
        :transcript-confirmation="chatApi.transcriptConfirmation.value"
        :correction-notice="chatApi.correctionNotice.value"
        :content-kind="guidedTour.contentKind.value"
        :answer-title="tourAnswerTitle"
        :tour-status="guidedTour.status.value"
        :tour-route="guidedTour.route.value"
        :tour-preview-route="guidedTour.previewRoute.value"
        :tour-stops="guidedTour.stops.value"
        :tour-position="guidedTour.position.value"
        :tour-active-stop="guidedTour.activeStop.value"
        :tour-dwell-progress="guidedTour.dwellProgress.value"
        :tour-speed="guidedTour.speedMultiplier.value"
        :location-mode="guidedTour.locationMode.value"
        :gps-status="guidedTour.gpsStatus.value"
        :tour-load-error="guidedTour.loadError.value"
        :requires-manual-play="guidedTour.requiresManualPlay.value"
        @ask="handleAsk"
        @mode-change="handleModeChange"
        @start-recording="handleStartRecording"
        @stop-recording="chatApi.stopRecording"
        @cancel="chatApi.cancelResponse"
        @confirm-transcript="chatApi.confirmTranscript"
        @avatar-change="chatApi.setAvatar"
        @toggle-history="historyOpen = true"
        @tour-start="guidedTour.start"
        @tour-pause="guidedTour.pause"
        @tour-resume="guidedTour.resume"
        @tour-speed-change="guidedTour.setSpeed"
        @tour-reset="guidedTour.reset"
        @location-mode-change="guidedTour.setLocationMode"
        @accept-preview-route="guidedTour.acceptAiRoute"
        @play-narration="guidedTour.playNarrationManually"
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
