import assert from "node:assert/strict";
import test from "node:test";

import { createRealtimeEventHandler } from "../src/lib/realtimeSessionEvents.js";
import {
  applyFailedActiveMessage,
  ensureAssistantMessage,
  ensureVoiceMessages,
  formatConfidence,
  latestUserText,
} from "../src/lib/realtimeTurnHelpers.js";

function createRef(value) {
  return { value };
}

function createCtx(overrides = {}) {
  const sent = [];
  const audio = {
    playbackActive: createRef(false),
    clearPlayback() {
      audio.cleared = true;
    },
    cleared: false,
  };
  const ctx = {
    mode: createRef("text"),
    messages: createRef([]),
    sources: createRef([]),
    confidence: createRef("--"),
    serviceState: createRef("正在连接"),
    avatarState: createRef("idle"),
    avatarId: createRef("mao_pro"),
    pendingAvatarId: createRef(""),
    avatarSynchronized: createRef(false),
    liveTranscript: createRef(""),
    assistantTranscript: createRef(""),
    activeTurnId: createRef("turn_1"),
    transcriptConfirmation: createRef(null),
    correctionNotice: createRef(""),
    currentSessionId: createRef(""),
    audio,
    sendJson(event) {
      sent.push(event);
    },
    onSessionChanged: null,
    sent,
    ...overrides,
  };
  return ctx;
}

test("formatConfidence renders percentages and falls back for invalid values", () => {
  assert.equal(formatConfidence(0.86), "86%");
  assert.equal(formatConfidence("bad"), "--");
});

test("ensureAssistantMessage creates or reuses the assistant turn row", () => {
  const messages = [];
  const created = ensureAssistantMessage(messages, "turn_1", "问路");
  assert.equal(messages.length, 1);
  assert.equal(created.retryQuestion, "问路");
  assert.equal(ensureAssistantMessage(messages, "turn_1"), created);
});

test("latestUserText returns the newest non-empty visitor message", () => {
  assert.equal(latestUserText([
    { role: "user", content: "第一问" },
    { role: "assistant", content: "第一答" },
    { role: "user", content: "  " },
    { role: "user", content: "你讲得真专业" },
    { role: "assistant", content: "谢谢" },
  ]), "你讲得真专业");
  assert.equal(latestUserText([{ role: "assistant", content: "没有游客消息" }]), "");
});

test("ensureVoiceMessages adds a voice user row once", () => {
  const messages = [];
  ensureVoiceMessages(messages, "turn_1", "灵山几点开门");
  ensureVoiceMessages(messages, "turn_1", "灵山几点开门");
  assert.equal(messages.filter((item) => item.role === "user").length, 1);
  assert.equal(messages.filter((item) => item.role === "assistant").length, 1);
});

test("applyFailedActiveMessage marks the active assistant turn as retryable", () => {
  const messages = [
    { id: "turn_1_user", role: "user", content: "问路" },
    { id: "turn_1", role: "assistant", content: "", pending: true },
  ];
  applyFailedActiveMessage(messages, "turn_1", "失败", true);
  assert.equal(messages[1].error, "失败");
  assert.equal(messages[1].retryable, true);
  assert.equal(messages[1].pending, false);
  assert.equal(messages[1].retryQuestion, "问路");
});

test("assistant text delta appends only for the active turn", () => {
  const ctx = createCtx();
  const { handleServerEvent } = createRealtimeEventHandler(ctx);
  handleServerEvent({ type: "assistant.text.delta", turn_id: "other", delta: "忽略" });
  assert.equal(ctx.messages.value.length, 0);
  handleServerEvent({ type: "assistant.text.delta", turn_id: "turn_1", delta: "你好" });
  assert.equal(ctx.messages.value[0].content, "你好");
  assert.equal(ctx.assistantTranscript.value, "你好");
});

test("turn.completed finalizes the active message and clears the turn", () => {
  const ctx = createCtx({
    sources: createRef([{ tool: "rag" }]),
    onSessionChanged() {
      ctx.sessionChanged = true;
    },
  });
  const { handleServerEvent } = createRealtimeEventHandler(ctx);
  handleServerEvent({ type: "assistant.text.delta", turn_id: "turn_1", delta: "完成稿" });
  handleServerEvent({ type: "turn.completed", turn_id: "turn_1" });
  assert.equal(ctx.activeTurnId.value, "");
  assert.equal(ctx.messages.value[0].pending, false);
  assert.deepEqual(ctx.messages.value[0].sources, [{ tool: "rag" }]);
  assert.equal(ctx.serviceState.value, "回答完成");
  assert.equal(ctx.sessionChanged, true);
});

test("stale turn.completed events are ignored", () => {
  const ctx = createCtx({ activeTurnId: createRef("turn_live") });
  const { handleServerEvent } = createRealtimeEventHandler(ctx);
  handleServerEvent({ type: "turn.completed", turn_id: "turn_old" });
  assert.equal(ctx.activeTurnId.value, "turn_live");
  assert.equal(ctx.messages.value.length, 0);
});

test("avatar.changed updates synchronized role state", () => {
  const previousStorage = globalThis.localStorage;
  const store = new Map();
  globalThis.localStorage = {
    getItem(key) {
      return store.has(key) ? store.get(key) : null;
    },
    setItem(key, value) {
      store.set(key, String(value));
    },
  };
  try {
    const ctx = createCtx({
      mode: createRef("avatar"),
      pendingAvatarId: createRef("chitose"),
      avatarSynchronized: createRef(false),
    });
    const { handleServerEvent } = createRealtimeEventHandler(ctx);
    handleServerEvent({ type: "avatar.changed", avatar_id: "chitose" });
    assert.equal(ctx.avatarId.value, "chitose");
    assert.equal(ctx.pendingAvatarId.value, "");
    assert.equal(ctx.avatarSynchronized.value, true);
    assert.equal(ctx.serviceState.value, "数字人已就绪");
  } finally {
    globalThis.localStorage = previousStorage;
  }
});
