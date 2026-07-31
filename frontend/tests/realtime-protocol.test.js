import assert from "node:assert/strict";
import test from "node:test";

import * as realtimeProtocol from "../src/lib/realtimeProtocol.js";
import {
  float32Metrics,
  float32ToInt16,
  pcmRms,
} from "../src/features/digital-human/lib/pcmAudio.js";

const { buildRealtimeUrl, responseModalities, resolveAvatarSyncTransition } = realtimeProtocol;

test("realtime URL keeps visitor and optional session identity", () => {
  const url = buildRealtimeUrl(
    { protocol: "https:", host: "example.test" },
    "visitor 1",
    "sess/1",
    "chitose",
  );

  assert.equal(
    url,
    "wss://example.test/api/visitor/realtime?visitor_id=visitor+1&session_id=sess%2F1&avatar_id=chitose",
  );
});

test("avatar synchronization commits only a confirmed server role", () => {
  const changing = resolveAvatarSyncTransition(
    { activeAvatarId: "mao_pro", pendingAvatarId: "chitose", synchronized: false },
    {
      type: "avatar.changing",
      active_avatar_id: "mao_pro",
      requested_avatar_id: "chitose",
    },
  );
  assert.deepEqual(changing, {
    activeAvatarId: "mao_pro",
    pendingAvatarId: "chitose",
    synchronized: false,
    persist: false,
  });

  const changed = resolveAvatarSyncTransition(changing, {
    type: "avatar.changed",
    avatar_id: "chitose",
  });
  assert.deepEqual(changed, {
    activeAvatarId: "chitose",
    pendingAvatarId: "",
    synchronized: true,
    persist: true,
  });
});

test("failed avatar synchronization retains the previous confirmed role", () => {
  const failed = resolveAvatarSyncTransition(
    { activeAvatarId: "mao_pro", pendingAvatarId: "chitose", synchronized: false },
    {
      type: "avatar.change_failed",
      active_avatar_id: "mao_pro",
      requested_avatar_id: "chitose",
    },
  );

  assert.deepEqual(failed, {
    activeAvatarId: "mao_pro",
    pendingAvatarId: "",
    synchronized: true,
    persist: false,
  });
});

test("mode maps to explicit output modalities", () => {
  assert.deepEqual(responseModalities("text"), ["text"]);
  assert.deepEqual(responseModalities("avatar"), ["audio", "text"]);
});

test("realtime mode is resynchronized after a socket becomes ready", () => {
  assert.equal(typeof realtimeProtocol.buildModeSetEvent, "function");
  assert.deepEqual(realtimeProtocol.buildModeSetEvent("avatar"), {
    type: "mode.set",
    mode: "avatar",
  });
});

test("avatar selection sends only an approved avatar identifier", () => {
  assert.equal(typeof realtimeProtocol.buildAvatarSetEvent, "function");
  assert.deepEqual(realtimeProtocol.buildAvatarSetEvent("chitose"), {
    type: "avatar.set",
    avatar_id: "chitose",
  });
  assert.deepEqual(realtimeProtocol.buildAvatarSetEvent("not-allowed"), {
    type: "avatar.set",
    avatar_id: "mao_pro",
  });
});

test("transcript confirmation sends the chosen or edited text for the same turn", () => {
  assert.deepEqual(
    realtimeProtocol.buildTranscriptConfirmEvent("turn_1", "鼋头渚几点开放"),
    {
      type: "transcript.confirm",
      turn_id: "turn_1",
      text: "鼋头渚几点开放",
    },
  );
});

test("digital human caption prefers the assistant answer over the user transcript", () => {
  assert.equal(typeof realtimeProtocol.resolveAvatarCaption, "function");
  assert.equal(realtimeProtocol.resolveAvatarCaption("景区回答", "用户问题"), "景区回答");
  assert.equal(realtimeProtocol.resolveAvatarCaption("", "用户问题"), "用户问题");
});

test("avatar remains speaking until browser playback ends after server completion", () => {
  assert.equal(typeof realtimeProtocol.resolveAvatarAudioState, "function");
  assert.equal(realtimeProtocol.resolveAvatarAudioState({
    eventType: "assistant.audio.done",
    playbackActive: true,
    turnActive: true,
  }), "speaking");
  assert.equal(realtimeProtocol.resolveAvatarAudioState({
    eventType: "turn.completed",
    playbackActive: true,
    turnActive: false,
  }), "speaking");
  assert.equal(realtimeProtocol.resolveAvatarAudioState({
    eventType: "playback.ended",
    playbackActive: false,
    turnActive: false,
  }), "idle");
  assert.equal(realtimeProtocol.resolveAvatarAudioState({
    eventType: "playback.ended",
    playbackActive: false,
    turnActive: true,
  }), "thinking");
});

test("queued browser playback keeps the stop action available after turn completion", () => {
  assert.equal(typeof realtimeProtocol.isRealtimeBusy, "function");
  assert.equal(realtimeProtocol.isRealtimeBusy("turn_1", false), true);
  assert.equal(realtimeProtocol.isRealtimeBusy("", true), true);
  assert.equal(realtimeProtocol.isRealtimeBusy("", false), false);
});

test("PCM conversion clamps samples and RMS reflects signal level", () => {
  const pcm = float32ToInt16(new Float32Array([-2, -0.5, 0, 0.5, 2]));

  assert.deepEqual(Array.from(pcm), [-32768, -16384, 0, 16383, 32767]);
  assert.ok(pcmRms(pcm) > 0.7);
  assert.equal(pcmRms(new Int16Array(10)), 0);
});

test("capture metrics report input RMS, peak and clipped sample ratio", () => {
  const metrics = float32Metrics(new Float32Array([0, 0.5, 0.99, -1]));

  assert.ok(metrics.rms > 0.7);
  assert.equal(metrics.peak, 1);
  assert.equal(metrics.clippedRatio, 0.5);
});
