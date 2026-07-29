import {
  buildAvatarSetEvent,
  buildModeSetEvent,
  resolveAvatarAudioState,
  resolveAvatarSyncTransition,
} from "./realtimeProtocol.js";
import {
  applyFailedActiveMessage,
  ensureAssistantMessage,
  ensureVoiceMessages,
  formatConfidence,
} from "./realtimeTurnHelpers.js";
import { normalizeAvatarId, saveAvatarPreference } from "../features/digital-human/lib/live2dCharacters.js";

/**
 * Build a server-event handler bound to a shared mutable realtime context.
 * Context refs must stay the same object identity for the lifetime of the socket.
 */
export function createRealtimeEventHandler(ctx) {
  function applyAvatarSyncTransition(event) {
    const next = resolveAvatarSyncTransition(
      {
        activeAvatarId: ctx.avatarId.value,
        pendingAvatarId: ctx.pendingAvatarId.value,
        synchronized: ctx.avatarSynchronized.value,
      },
      event,
    );
    ctx.avatarId.value = next.persist
      ? saveAvatarPreference(globalThis.localStorage, next.activeAvatarId)
      : next.activeAvatarId;
    ctx.pendingAvatarId.value = next.pendingAvatarId;
    ctx.avatarSynchronized.value = next.synchronized;
  }

  function failActiveMessage(message, retryable) {
    // Stop buffered speech on failures so an error state cannot keep talking with stale lip movement.
    ctx.audio.clearPlayback();
    applyFailedActiveMessage(ctx.messages.value, ctx.activeTurnId.value, message, retryable);
    ctx.activeTurnId.value = "";
    ctx.avatarState.value = "error";
  }

  function handleServerEvent(event) {
    if (event.type === "session.ready") {
      // Reassert local mode after every connection because mode changes made while connecting are otherwise lost.
      ctx.sendJson(buildModeSetEvent(ctx.mode.value));
      const readyAvatarId = normalizeAvatarId(event.avatar_id);
      ctx.avatarSynchronized.value = Boolean(
        event.upstream_available && readyAvatarId === ctx.avatarId.value,
      );
      ctx.pendingAvatarId.value = "";
      if (event.upstream_available && readyAvatarId !== ctx.avatarId.value) {
        ctx.pendingAvatarId.value = ctx.avatarId.value;
        ctx.sendJson(buildAvatarSetEvent(ctx.avatarId.value));
      }
      if (!event.upstream_available) {
        ctx.serviceState.value = "语音服务暂不可用，可继续尝试文字回答";
      }
      return;
    }
    if (event.type === "avatar.changing") {
      applyAvatarSyncTransition(event);
      ctx.serviceState.value = "正在建立角色专属语音连接";
      return;
    }
    if (event.type === "avatar.changed") {
      applyAvatarSyncTransition(event);
      ctx.serviceState.value = ctx.mode.value === "avatar" ? "数字人已就绪" : ctx.serviceState.value;
      return;
    }
    if (event.type === "avatar.change_failed") {
      applyAvatarSyncTransition(event);
      ctx.serviceState.value = event.message || "数字人角色切换失败，已保留原角色";
      ctx.avatarState.value = "error";
      return;
    }
    if (event.type === "session.bound" && event.session_id) {
      ctx.currentSessionId.value = event.session_id;
      localStorage.setItem("lingjing_current_session_id", event.session_id);
      return;
    }
    if (event.type === "user.transcript.delta") {
      if (event.turn_id && event.turn_id !== ctx.activeTurnId.value) return;
      ctx.liveTranscript.value += event.delta || "";
      return;
    }
    if (event.type === "user.transcript.done") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.liveTranscript.value = event.text || ctx.liveTranscript.value;
      ensureVoiceMessages(ctx.messages.value, event.turn_id, ctx.liveTranscript.value);
      ctx.transcriptConfirmation.value = null;
      ctx.correctionNotice.value = event.correction?.applied ? "已按景区词典纠正" : "";
      ctx.avatarState.value = "thinking";
      return;
    }
    if (event.type === "user.transcript.confirmation_required") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.transcriptConfirmation.value = {
        turnId: event.turn_id,
        text: event.text || ctx.liveTranscript.value,
        candidates: event.candidates || [],
      };
      ctx.liveTranscript.value = ctx.transcriptConfirmation.value.text;
      ctx.avatarState.value = "idle";
      ctx.serviceState.value = "转写结果需要确认";
      return;
    }
    if (event.type === "agent.meta") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.sources.value = event.sources || [];
      ctx.confidence.value = formatConfidence(event.confidence);
      return;
    }
    if (event.type === "assistant.text.delta") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      const delta = event.delta || "";
      ensureAssistantMessage(ctx.messages.value, event.turn_id).content += delta;
      ctx.assistantTranscript.value += delta;
      return;
    }
    if (event.type === "assistant.text.done") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      const message = ensureAssistantMessage(ctx.messages.value, event.turn_id);
      message.content = event.text || message.content;
      ctx.assistantTranscript.value = message.content;
      return;
    }
    if (event.type === "turn.reset") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      const message = ensureAssistantMessage(ctx.messages.value, event.turn_id);
      message.content = "";
      ctx.audio.clearPlayback();
      ctx.avatarState.value = "thinking";
      ctx.serviceState.value = "连接已恢复，正在重新生成";
      return;
    }
    if (event.type === "assistant.audio.started") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.avatarState.value = resolveAvatarAudioState({
        eventType: event.type,
        playbackActive: ctx.audio.playbackActive.value,
        turnActive: true,
      });
      return;
    }
    if (event.type === "assistant.audio.done") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.avatarState.value = resolveAvatarAudioState({
        eventType: event.type,
        playbackActive: ctx.audio.playbackActive.value,
        turnActive: true,
      });
      return;
    }
    if (event.type === "turn.completed") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      const message = ensureAssistantMessage(ctx.messages.value, event.turn_id);
      message.pending = false;
      message.sources = ctx.sources.value;
      ctx.activeTurnId.value = "";
      ctx.avatarState.value = resolveAvatarAudioState({
        eventType: event.type,
        playbackActive: ctx.audio.playbackActive.value,
        turnActive: false,
      });
      ctx.serviceState.value = "回答完成";
      ctx.onSessionChanged?.();
      return;
    }
    if (event.type === "turn.cancelled") {
      if (event.turn_id !== ctx.activeTurnId.value) return;
      ctx.audio.clearPlayback();
      ctx.activeTurnId.value = "";
      ctx.avatarState.value = "idle";
      return;
    }
    if (event.type === "error") {
      ctx.serviceState.value = event.message || "实时服务异常";
      if (!event.recoverable) failActiveMessage(ctx.serviceState.value, true);
    }
  }

  return { handleServerEvent, failActiveMessage };
}
