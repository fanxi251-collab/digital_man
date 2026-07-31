import { computed, onBeforeUnmount, ref } from "vue";
import {
  buildModeSetEvent,
  buildAvatarSetEvent,
  buildRealtimeUrl,
  buildTranscriptConfirmEvent,
  createTurnId,
  isRealtimeBusy,
  resolveAvatarAudioState,
  resolveAvatarCaption,
} from "../lib/realtimeProtocol";
import { createRealtimeEventHandler } from "../lib/realtimeSessionEvents.js";
import {
  createTailProtection,
  loadAvatarPreference,
  normalizeAvatarId,
  usePcmAudio,
} from "../features/digital-human";
import { findSuccessfulRouteSource, resolveRouteSummary } from "../lib/routeSummary.js";
import { latestUserText as resolveLatestUserText } from "../lib/realtimeTurnHelpers.js";

export function useRealtimeChat({ currentSessionId, visitorId, onSessionChanged }) {
  const mode = ref("text");
  const messages = ref([]);
  const sources = ref([]);
  const confidence = ref("--");
  const serviceState = ref("正在连接");
  const avatarState = ref("idle");
  const avatarId = ref(loadAvatarPreference());
  const pendingAvatarId = ref("");
  const avatarSynchronized = ref(false);
  const liveTranscript = ref("");
  const assistantTranscript = ref("");
  const activeTurnId = ref("");
  const socketState = ref("closed");
  const transcriptConfirmation = ref(null);
  const correctionNotice = ref("");
  let socket = null;
  let connectPromise = null;
  let stopRecordingRequested = false;
  let capturedAudioChunks = 0;
  const tailProtection = createTailProtection();
  // 浏览器 WS 有限次自动重连：与后端 turn.reset 对齐，避免闪断立即判失败。
  const MAX_BROWSER_RECONNECT = 3;
  let intentionalDisconnect = false;
  let reconnectAttempts = 0;
  let reconnectTimer = null;
  let lastConnectSessionId = currentSessionId.value;

  const audio = usePcmAudio({
    onCaptureChunk: (chunk) => {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(chunk);
        capturedAudioChunks += 1;
      }
    },
    onPlaybackStateChange: (active) => {
      // Browser playback owns the speaking state because upstream completion can arrive before sound ends.
      avatarState.value = resolveAvatarAudioState({
        eventType: active ? "playback.started" : "playback.ended",
        playbackActive: active,
        turnActive: Boolean(activeTurnId.value),
      });
    },
  });

  function sendJson(event) {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify(event));
  }

  const { handleServerEvent, failActiveMessage } = createRealtimeEventHandler({
    mode,
    messages,
    sources,
    confidence,
    serviceState,
    avatarState,
    avatarId,
    pendingAvatarId,
    avatarSynchronized,
    liveTranscript,
    assistantTranscript,
    activeTurnId,
    transcriptConfirmation,
    correctionNotice,
    currentSessionId,
    audio,
    sendJson,
    onSessionChanged,
  });

  const isLoading = computed(() => isRealtimeBusy(activeTurnId.value, audio.playbackActive.value));
  const avatarReady = computed(() =>
    mode.value !== "avatar"
    || (avatarSynchronized.value && !pendingAvatarId.value),
  );
  const avatarCaption = computed(() =>
    resolveAvatarCaption(assistantTranscript.value, liveTranscript.value),
  );
  const latestRouteSummary = computed(() => {
    const source = findSuccessfulRouteSource(sources.value);
    return source ? resolveRouteSummary(source) : null;
  });
  const hasRouteSource = computed(() => Boolean(latestRouteSummary.value));
  const latestUserText = computed(() => resolveLatestUserText(messages.value));

  function clearReconnectTimer() {
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function closeSocketOnly() {
    if (!socket) return;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    socket.close();
    socket = null;
  }

  function scheduleReconnect(sessionId) {
    if (intentionalDisconnect || reconnectAttempts >= MAX_BROWSER_RECONNECT) {
      socketState.value = "closed";
      avatarSynchronized.value = false;
      pendingAvatarId.value = "";
      if (activeTurnId.value) failActiveMessage("连接已断开，请重试。", true);
      return;
    }
    reconnectAttempts += 1;
    const delayMs = 500 * (2 ** (reconnectAttempts - 1));
    socketState.value = "connecting";
    serviceState.value = `连接断开，正在重连（${reconnectAttempts}/${MAX_BROWSER_RECONNECT}）`;
    clearReconnectTimer();
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      connect(sessionId, { fromReconnect: true });
    }, delayMs);
  }

  function connect(sessionId = currentSessionId.value, options = {}) {
    const fromReconnect = Boolean(options.fromReconnect);
    lastConnectSessionId = sessionId;
    clearReconnectTimer();
    if (!fromReconnect) {
      intentionalDisconnect = false;
      reconnectAttempts = 0;
    }
    // 重建 socket 时不标 intentional，避免打断自动重连预算。
    closeSocketOnly();
    // Every socket must re-acknowledge the role so a reconnect cannot reuse stale voice state.
    avatarSynchronized.value = false;
    pendingAvatarId.value = "";
    socketState.value = "connecting";
    connectPromise = new Promise((resolve) => {
      socket = new WebSocket(
        buildRealtimeUrl(window.location, visitorId, sessionId, avatarId.value),
      );
      socket.binaryType = "arraybuffer";
      socket.onopen = () => {
        reconnectAttempts = 0;
        socketState.value = "open";
        serviceState.value = fromReconnect ? "连接已恢复" : "智能导游在线";
        resolve();
      };
      socket.onmessage = async ({ data }) => {
        if (data instanceof ArrayBuffer) {
          try {
            await audio.enqueuePlayback(data);
          } catch {
            // Keep text usable when browser autoplay or the selected output device rejects PCM playback.
            avatarState.value = "error";
            serviceState.value = "语音播放失败，回答字幕仍可查看";
          }
          return;
        }
        try {
          handleServerEvent(JSON.parse(data));
        } catch {
          serviceState.value = "收到异常消息，已忽略该帧";
        }
      };
      socket.onerror = () => {
        serviceState.value = "连接异常，正在等待恢复";
        socketState.value = "error";
        resolve();
      };
      socket.onclose = () => {
        socket = null;
        if (intentionalDisconnect) {
          socketState.value = "closed";
          avatarSynchronized.value = false;
          pendingAvatarId.value = "";
          resolve();
          return;
        }
        scheduleReconnect(lastConnectSessionId);
        resolve();
      };
    });
    return connectPromise;
  }

  async function ensureConnected() {
    if (socket?.readyState === WebSocket.OPEN) return;
    if (socketState.value !== "connecting") connect();
    await connectPromise;
    if (socket?.readyState !== WebSocket.OPEN) throw new Error("实时连接尚未建立");
  }

  async function ask(text) {
    const question = String(text || "").trim();
    if (!question) return;
    try {
      if (mode.value === "avatar") {
        audio.preparePlayback().catch(() => {
          serviceState.value = "浏览器暂未允许语音播放，将继续显示回答字幕";
        });
      }
      await ensureConnected();
      ensureAvatarReady();
      if (activeTurnId.value) cancelResponse();
      const turnId = createTurnId();
      activeTurnId.value = turnId;
      messages.value.push({ id: `${turnId}_user`, role: "user", content: question });
      messages.value.push({
        id: turnId,
        role: "assistant",
        content: "",
        pending: true,
        retryQuestion: question,
      });
      sources.value = [];
      confidence.value = "--";
      liveTranscript.value = question;
      assistantTranscript.value = "";
      avatarState.value = "thinking";
      serviceState.value = "正在检索景区资料";
      sendJson({ type: "text.submit", turn_id: turnId, text: question });
    } catch (error) {
      failActiveMessage(error.message || "发送失败，请重试。", true);
    }
  }

  async function startRecording() {
    let recordingTurnId = "";
    try {
      stopRecordingRequested = false;
      tailProtection.cancel();
      capturedAudioChunks = 0;
      audio.preparePlayback().catch(() => {
        serviceState.value = "浏览器暂未允许语音播放，将继续显示回答字幕";
      });
      await ensureConnected();
      ensureAvatarReady();
      cancelResponse();
      const turnId = createTurnId();
      recordingTurnId = turnId;
      activeTurnId.value = turnId;
      liveTranscript.value = "";
      assistantTranscript.value = "";
      transcriptConfirmation.value = null;
      correctionNotice.value = "";
      avatarState.value = "listening";
      sendJson({ type: "audio.start", turn_id: turnId });
      await audio.startCapture();
      if (stopRecordingRequested) {
        await audio.stopCapture();
        sendJson({ type: "response.cancel", turn_id: turnId });
        activeTurnId.value = "";
        avatarState.value = "idle";
        serviceState.value = "麦克风已就绪，请重新按住说话";
        return;
      }
      serviceState.value = "正在聆听，松开发送";
    } catch {
      if (recordingTurnId) {
        sendJson({ type: "response.cancel", turn_id: recordingTurnId });
      }
      if (activeTurnId.value !== recordingTurnId) return;
      avatarState.value = "error";
      serviceState.value = "麦克风不可用，请使用文字输入";
      activeTurnId.value = "";
    }
  }

  async function stopRecording() {
    if (audio.microphoneState.value === "starting") {
      stopRecordingRequested = true;
      serviceState.value = "正在启动麦克风，完成后请重新按住说话";
      return;
    }
    if (audio.microphoneState.value !== "recording" || !activeTurnId.value) return;
    const turnId = activeTurnId.value;
    audio.beginFinishing();
    serviceState.value = "正在补全句尾语音";
    tailProtection.start(async () => {
      await audio.stopCapture();
      if (turnId !== activeTurnId.value) return;
      const quality = audio.captureSnapshot();
      if (!capturedAudioChunks || quality.voicedDurationMs < 300) {
        sendJson({ type: "response.cancel", turn_id: turnId });
        activeTurnId.value = "";
        avatarState.value = "idle";
        serviceState.value = "未检测到完整语音，请按住按钮说完后再松开";
        return;
      }
      if (quality.severeClipping) {
        sendJson({ type: "response.cancel", turn_id: turnId });
        activeTurnId.value = "";
        avatarState.value = "error";
        serviceState.value = "录音音量过大，请稍微远离麦克风后重试";
        return;
      }
      sendJson({ type: "audio.commit", turn_id: turnId });
      avatarState.value = "thinking";
      serviceState.value = quality.inputQuality === "quiet"
        ? "正在识别语音（录音音量偏低）"
        : "正在识别语音";
    });
  }

  function setMode(nextMode) {
    if (!['text', 'avatar'].includes(nextMode) || nextMode === mode.value) return;
    cancelResponse();
    mode.value = nextMode;
    liveTranscript.value = "";
    assistantTranscript.value = "";
    sendJson(buildModeSetEvent(nextMode));
    serviceState.value = nextMode === "avatar" ? "数字人已就绪" : "常规对话已就绪";
    avatarState.value = "idle";
  }

  function setAvatar(nextAvatarId) {
    const normalized = normalizeAvatarId(nextAvatarId);
    if (normalized === avatarId.value || pendingAvatarId.value) return;
    cancelResponse();
    pendingAvatarId.value = normalized;
    avatarSynchronized.value = false;
    sendJson(buildAvatarSetEvent(normalized));
    serviceState.value = "正在切换数字人形象";
    avatarState.value = "idle";
  }

  function ensureAvatarReady() {
    if (mode.value === "avatar" && !avatarSynchronized.value) {
      serviceState.value = "正在同步数字人角色，请稍候";
      throw new Error("数字人角色尚未同步完成");
    }
  }

  function cancelResponse() {
    tailProtection.cancel();
    transcriptConfirmation.value = null;
    if (!isRealtimeBusy(activeTurnId.value, audio.playbackActive.value)) return;
    stopRecordingRequested = true;
    if (activeTurnId.value) {
      sendJson({ type: "response.cancel", turn_id: activeTurnId.value });
    }
    audio.stopCapture();
    audio.clearPlayback();
    activeTurnId.value = "";
    avatarState.value = "idle";
  }

  function confirmTranscript(text) {
    const pending = transcriptConfirmation.value;
    const confirmed = String(text || "").trim();
    if (!pending || !confirmed) return;
    sendJson(buildTranscriptConfirmEvent(pending.turnId, confirmed));
    transcriptConfirmation.value = null;
    liveTranscript.value = confirmed;
    avatarState.value = "thinking";
    serviceState.value = "正在检索景区资料";
  }

  function restoreMessages(storedMessages) {
    messages.value = (storedMessages || []).map((message) => ({
      id: `stored_${message.message_id}`,
      role: message.role,
      content: message.content,
      sources: message.sources || [],
    }));
    const lastAssistant = [...(storedMessages || [])].reverse().find((item) => item.role === "assistant");
    sources.value = lastAssistant?.sources || [];
    connect(currentSessionId.value);
    serviceState.value = "历史会话已载入";
  }

  function resetConversation(message) {
    cancelResponse();
    messages.value = [];
    sources.value = [];
    confidence.value = "--";
    liveTranscript.value = "";
    assistantTranscript.value = "";
    connect("");
    serviceState.value = message || "已开启新会话";
  }

  function disconnect(clearAudio = true) {
    intentionalDisconnect = true;
    clearReconnectTimer();
    reconnectAttempts = 0;
    tailProtection.cancel();
    if (clearAudio) audio.clearPlayback();
    closeSocketOnly();
    socketState.value = "closed";
  }

  function suspendForRoute() {
    tailProtection.cancel();
    stopRecordingRequested = true;
    // 缓存页面离场时只释放麦克风与扬声器，保留 WebSocket 让正在生成的文字回答能够继续完成。
    audio.stopCapture();
    audio.clearPlayback();
    if (avatarState.value === "listening" || avatarState.value === "speaking") {
      avatarState.value = activeTurnId.value ? "thinking" : "idle";
    }
  }

  function markKnowledgeUpdated() {
    serviceState.value = "资料已更新";
  }

  connect();
  onBeforeUnmount(async () => {
    disconnect();
    await audio.dispose();
  });

  return {
    mode,
    messages,
    sources,
    confidence,
    serviceState,
    avatarState,
    avatarId,
    pendingAvatarId,
    avatarSynchronized,
    avatarReady,
    liveTranscript,
    assistantTranscript,
    transcriptConfirmation,
    correctionNotice,
    avatarCaption,
    isLoading,
    hasRouteSource,
    latestRouteSummary,
    latestUserText,
    audioLevel: audio.audioLevel,
    inputLevel: audio.inputLevel,
    inputQuality: audio.inputQuality,
    autoGainState: audio.autoGainState,
    microphoneState: audio.microphoneState,
    ask,
    startRecording,
    stopRecording,
    setMode,
    setAvatar,
    cancelResponse,
    confirmTranscript,
    restoreMessages,
    resetConversation,
    markKnowledgeUpdated,
    suspendForRoute,
  };
}
