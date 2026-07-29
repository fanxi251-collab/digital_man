import assert from "node:assert/strict";
import test from "node:test";

import { usePcmAudio } from "../src/features/digital-human/composables/usePcmAudio.js";
import {
  TAIL_PROTECTION_MS,
  createCaptureQualityTracker,
  createTailProtection,
} from "../src/features/digital-human/lib/audioCaptureQuality.js";

function installPlaybackFakes() {
  const sources = [];
  const animationFrames = new Map();
  const pendingTimeouts = new Map();
  const analyser = {
    samples: new Float32Array(512),
    connect(target) { this.connectedTo = target; },
    disconnect() { this.disconnected = true; },
    getFloatTimeDomainData(target) { target.set(this.samples); },
  };
  let nextAnimationFrame = 0;
  let nextTimeout = 0;

  class FakeAudioContext {
    constructor() {
      this.currentTime = 0;
      this.destination = {};
      this.state = "running";
    }

    createBuffer(_channels, length, sampleRate) {
      return {
        duration: length / sampleRate,
        getChannelData: () => new Float32Array(length),
      };
    }

    createBufferSource() {
      const source = {
        connect(target) { source.connectedTo = target; },
        start() {},
        stop() { source.stopped = true; },
        finish() { source.onended?.(); },
      };
      sources.push(source);
      return source;
    }

    createAnalyser() { return analyser; }

    async resume() {}
    async close() {}
  }

  Object.defineProperty(globalThis, "AudioContext", {
    configurable: true,
    value: FakeAudioContext,
  });
  Object.defineProperty(globalThis, "requestAnimationFrame", {
    configurable: true,
    value(callback) {
      nextAnimationFrame += 1;
      animationFrames.set(nextAnimationFrame, callback);
      return nextAnimationFrame;
    },
  });
  Object.defineProperty(globalThis, "cancelAnimationFrame", {
    configurable: true,
    value(handle) { animationFrames.delete(handle); },
  });
  // 合并窗依赖 setTimeout：测试里改为可冲刷队列，避免真实等待 60ms。
  Object.defineProperty(globalThis, "setTimeout", {
    configurable: true,
    value(callback) {
      nextTimeout += 1;
      pendingTimeouts.set(nextTimeout, callback);
      return nextTimeout;
    },
  });
  Object.defineProperty(globalThis, "clearTimeout", {
    configurable: true,
    value(handle) { pendingTimeouts.delete(handle); },
  });
  return {
    analyser,
    animationFrames,
    sources,
    async flushMergeTimers() {
      const callbacks = [...pendingTimeouts.values()];
      pendingTimeouts.clear();
      for (const callback of callbacks) {
        await callback();
      }
    },
    runAnimationFrame(samples) {
      analyser.samples.fill(0);
      analyser.samples.set(samples);
      const entry = animationFrames.entries().next().value;
      assert.ok(entry, "expected a scheduled playback analysis frame");
      animationFrames.delete(entry[0]);
      entry[1]();
    },
  };
}

test("microphone exposes a starting state while browser permission is pending", async () => {
  let rejectPermission;
  const permission = new Promise((resolve, reject) => {
    rejectPermission = reject;
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia: () => permission } },
  });
  const audio = usePcmAudio({ onCaptureChunk() {} });

  const capture = audio.startCapture();
  const stateWhileWaiting = audio.microphoneState.value;
  rejectPermission(new Error("permission denied for test"));
  await assert.rejects(capture);

  assert.equal(stateWhileWaiting, "starting");
  assert.equal(audio.microphoneState.value, "denied");
});

test("microphone requests browser gain, echo, noise and mono processing", async () => {
  let requestedConstraints;
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      mediaDevices: {
        getUserMedia: (constraints) => {
          requestedConstraints = constraints;
          return Promise.reject(new Error("stop after inspecting constraints"));
        },
      },
    },
  });
  const audio = usePcmAudio({ onCaptureChunk() {} });

  await assert.rejects(audio.startCapture());

  assert.deepEqual(requestedConstraints.audio, {
    channelCount: 1,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  });
});

test("capture quality tracks speech, low volume and sustained clipping", () => {
  const quality = createCaptureQualityTracker();

  quality.add({ rms: 0.018, peak: 0.4, clippedRatio: 0 });
  quality.add({ rms: 0.021, peak: 0.5, clippedRatio: 0 });
  quality.add({ rms: 0.03, peak: 1, clippedRatio: 0.02 });
  quality.add({ rms: 0.03, peak: 1, clippedRatio: 0.02 });
  quality.add({ rms: 0.03, peak: 1, clippedRatio: 0.02 });

  assert.equal(quality.snapshot().inputQuality, "loud");
  assert.equal(quality.snapshot().severeClipping, true);
  assert.equal(quality.snapshot().voicedDurationMs, 500);
});

test("capture quality rejects short silence but submits quiet speech", () => {
  const silence = createCaptureQualityTracker();
  silence.add({ rms: 0.001, peak: 0.002, clippedRatio: 0 });
  silence.add({ rms: 0.001, peak: 0.002, clippedRatio: 0 });
  assert.equal(silence.snapshot().canCommit, false);

  const quietSpeech = createCaptureQualityTracker();
  quietSpeech.add({ rms: 0.01, peak: 0.05, clippedRatio: 0 });
  quietSpeech.add({ rms: 0.01, peak: 0.05, clippedRatio: 0 });
  quietSpeech.add({ rms: 0.01, peak: 0.05, clippedRatio: 0 });
  assert.equal(quietSpeech.snapshot().canCommit, true);
  assert.equal(quietSpeech.snapshot().inputQuality, "quiet");
  assert.equal(TAIL_PROTECTION_MS, 300);
});

test("tail protection finishes after 300ms and cancellation suppresses commit", async () => {
  const scheduled = [];
  const tail = createTailProtection({
    schedule(callback, delay) {
      scheduled.push({ callback, delay, cancelled: false });
      return scheduled.length - 1;
    },
    cancel(handle) {
      scheduled[handle].cancelled = true;
    },
  });
  let commits = 0;

  tail.start(() => { commits += 1; });
  assert.equal(scheduled[0].delay, 300);
  tail.cancel();
  if (!scheduled[0].cancelled) await scheduled[0].callback();
  assert.equal(commits, 0);

  tail.start(() => { commits += 1; });
  await scheduled[1].callback();
  assert.equal(commits, 1);
  assert.equal(tail.active(), false);
});

test("playback remains active until the final queued PCM source ends", async () => {
  const { sources, flushMergeTimers } = installPlaybackFakes();
  const playbackStates = [];
  const audio = usePcmAudio({
    onCaptureChunk() {},
    onPlaybackStateChange(active) { playbackStates.push(active); },
  });
  const pcm = new Int16Array([1000, -1000, 500, -500]).buffer;

  await audio.enqueuePlayback(pcm);
  await audio.enqueuePlayback(pcm);
  await audio.enqueuePlayback(pcm);
  await flushMergeTimers();

  assert.equal(audio.playbackActive.value, true);
  assert.deepEqual(playbackStates, [true]);
  // 三块在合并窗内合成一个 BufferSource。
  assert.equal(sources.length, 1);
  sources[0].finish();
  assert.equal(audio.playbackActive.value, false);
  assert.deepEqual(playbackStates, [true, false]);
});

test("playback analyser continuously follows the audio sent to the speakers", async () => {
  const { analyser, animationFrames, flushMergeTimers, runAnimationFrame, sources } = installPlaybackFakes();
  const audio = usePcmAudio({ onCaptureChunk() {} });

  await audio.enqueuePlayback(new Int16Array([1000, -1000]).buffer);
  await flushMergeTimers();
  assert.equal(sources[0].connectedTo, analyser);
  assert.equal(analyser.fftSize, 512);
  assert.equal(animationFrames.size, 1);

  runAnimationFrame(new Float32Array(512).fill(0.1));
  assert.ok(audio.audioLevel.value > 0.31 && audio.audioLevel.value < 0.33);
  runAnimationFrame(new Float32Array(512));
  assert.equal(audio.audioLevel.value, 0);

  audio.clearPlayback();
  assert.equal(audio.audioLevel.value, 0);
  assert.equal(audio.playbackActive.value, false);
  assert.equal(animationFrames.size, 0);
});

test("a cancelled queue cannot end a newer playback generation", async () => {
  const { animationFrames, flushMergeTimers, sources } = installPlaybackFakes();
  const states = [];
  const audio = usePcmAudio({
    onCaptureChunk() {},
    onPlaybackStateChange(active) { states.push(active); },
  });
  const pcm = new Int16Array([800, -800]).buffer;

  await audio.enqueuePlayback(pcm);
  await flushMergeTimers();
  audio.clearPlayback();
  await audio.enqueuePlayback(pcm);
  await flushMergeTimers();
  sources[0].finish();

  assert.equal(audio.playbackActive.value, true);
  assert.equal(animationFrames.size, 1);
  sources[1].finish();
  assert.equal(audio.playbackActive.value, false);
  assert.deepEqual(states, [true, false, true, false]);
});

test("small PCM chunks merge into one BufferSource inside the jitter window", async () => {
  const { flushMergeTimers, sources } = installPlaybackFakes();
  const audio = usePcmAudio({ onCaptureChunk() {} });
  const pcm = new Int16Array([100, -100]).buffer;

  await audio.enqueuePlayback(pcm);
  await audio.enqueuePlayback(pcm);
  assert.equal(sources.length, 0);
  await flushMergeTimers();
  assert.equal(sources.length, 1);
});
