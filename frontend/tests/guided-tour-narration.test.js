import assert from "node:assert/strict";
import test from "node:test";

import { createScenicNarration } from "../src/features/guided-tour/composables/useScenicNarration.js";

const coreStop = {
  stop_id: "grand-buddha",
  attraction_name: "灵山大佛",
  narration_text: "灵山大佛固定讲解。",
  local_audio_url: "/digital-human/narration/xiaoxiao/grand-buddha.mp3",
};

function response(ok, label = "audio") {
  return {
    ok,
    status: ok ? 200 : 404,
    async blob() {
      return { label, type: "audio/mpeg" };
    },
  };
}

function audioFactory(behaviors = ["ended"]) {
  const instances = [];
  return {
    instances,
    create(url) {
      const listeners = new Map();
      const behavior = behaviors[instances.length] || "ended";
      const audio = {
        url,
        currentTime: 0,
        paused: false,
        addEventListener(type, callback) { listeners.set(type, callback); },
        removeEventListener(type) { listeners.delete(type); },
        async play() {
          if (behavior === "blocked") {
            const error = new Error("autoplay blocked");
            error.name = "NotAllowedError";
            throw error;
          }
          queueMicrotask(() => listeners.get(behavior)?.());
        },
        pause() { this.paused = true; },
      };
      instances.push(audio);
      return audio;
    },
  };
}

test("local narration audio is preferred and retained as visible text", async () => {
  const calls = [];
  const audio = audioFactory();
  const revoked = [];
  const narration = createScenicNarration({
    fetcher: async (url, options) => {
      calls.push([url, options]);
      return response(true, "local");
    },
    audioFactory: audio.create,
    createObjectURL: (blob) => `blob:${blob.label}`,
    revokeObjectURL: (url) => revoked.push(url),
    levelMonitorFactory: () => ({ start() {}, stop() {}, dispose() {} }),
  });

  const result = await narration.play(coreStop);
  assert.equal(result.status, "complete");
  assert.equal(narration.text.value, "灵山大佛固定讲解。");
  assert.equal(narration.title.value, "灵山大佛");
  assert.equal(narration.source.value, "local");
  assert.deepEqual(calls, [[coreStop.local_audio_url, undefined]]);
  assert.deepEqual(revoked, ["blob:local"]);
  narration.dispose();
});

test("missing local audio falls back to the stop whitelist synthesis endpoint", async () => {
  const calls = [];
  const audio = audioFactory();
  const narration = createScenicNarration({
    fetcher: async (url, options) => {
      calls.push([url, options]);
      return calls.length === 1 ? response(false) : response(true, "online");
    },
    audioFactory: audio.create,
    createObjectURL: (blob) => `blob:${blob.label}`,
    revokeObjectURL() {},
    levelMonitorFactory: () => ({ start() {}, stop() {}, dispose() {} }),
  });

  const result = await narration.play(coreStop);
  assert.equal(result.status, "complete");
  assert.equal(narration.source.value, "online");
  assert.equal(
    calls[1][0],
    "/api/visitor/guided-tour/narrations/stops/grand-buddha/synthesize",
  );
  assert.equal(calls[1][1].method, "POST");
});

test("published attraction fallback never submits arbitrary narration text", async () => {
  const calls = [];
  const narration = createScenicNarration({
    fetcher: async (url, options) => {
      calls.push([url, options]);
      return response(true, "published");
    },
    audioFactory: audioFactory().create,
    createObjectURL: () => "blob:published",
    revokeObjectURL() {},
    levelMonitorFactory: () => ({ start() {}, stop() {}, dispose() {} }),
  });

  await narration.play({
    attraction_id: "attr-1",
    attraction_name: "公开景点",
    narration_text: "公开摘要",
  });
  assert.equal(
    calls[0][0],
    "/api/visitor/guided-tour/narrations/attractions/attr-1/synthesize",
  );
  assert.deepEqual(calls[0][1], { method: "POST" });
});

test("audio failures degrade to text without hiding the narration", async () => {
  const narration = createScenicNarration({
    fetcher: async () => response(false),
    audioFactory: audioFactory().create,
    createObjectURL: () => "unused",
    revokeObjectURL() {},
    levelMonitorFactory: () => ({ start() {}, stop() {}, dispose() {} }),
  });
  const result = await narration.play(coreStop);
  assert.equal(result.status, "text_only");
  assert.equal(narration.state.value, "complete");
  assert.equal(narration.source.value, "text");
  assert.equal(narration.text.value, coreStop.narration_text);
});

test("autoplay rejection exposes manual playback and cleanup releases resources", async () => {
  const audio = audioFactory(["blocked", "ended"]);
  const revoked = [];
  const narration = createScenicNarration({
    fetcher: async () => response(true, "local"),
    audioFactory: audio.create,
    createObjectURL: (blob) => `blob:${blob.label}`,
    revokeObjectURL: (url) => revoked.push(url),
    levelMonitorFactory: () => ({ start() {}, stop() {}, dispose() {} }),
  });

  const blocked = await narration.play(coreStop);
  assert.equal(blocked.status, "blocked");
  assert.equal(narration.requiresManualPlay.value, true);
  const completed = await narration.playManually();
  assert.equal(completed.status, "complete");
  assert.equal(narration.requiresManualPlay.value, false);
  narration.dispose();
  assert.equal(narration.audioLevel.value, 0);
  assert.deepEqual(revoked, ["blob:local"]);
});
