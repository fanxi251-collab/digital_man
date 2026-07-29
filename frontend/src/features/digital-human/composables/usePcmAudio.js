import { ref } from "vue";
import { createCaptureQualityTracker } from "../lib/audioCaptureQuality.js";
import { float32Metrics } from "../lib/pcmAudio.js";

// 约 60ms 合并窗：减少过碎 BufferSource，同时不拉高可感播放延迟。
const PLAYBACK_MERGE_WINDOW_MS = 60;
// 24kHz * 2 bytes * 80ms ≈ 上限，防止单次合并过大。
const PLAYBACK_MERGE_MAX_BYTES = 24000 * 2 * 0.08;

export function usePcmAudio({ onCaptureChunk, onPlaybackStateChange }) {
  const audioLevel = ref(0);
  const playbackActive = ref(false);
  const inputLevel = ref(0);
  const inputQuality = ref("good");
  const autoGainState = ref("unknown");
  const microphoneState = ref("idle");
  const qualityTracker = createCaptureQualityTracker();
  let captureContext = null;
  let captureStream = null;
  let captureNode = null;
  let playbackContext = null;
  let playbackAnalyser = null;
  let playbackAnalysisFrame = null;
  let playbackAnalysisSamples = null;
  let playbackCursor = 0;
  let playbackGeneration = 0;
  const playbackSources = new Set();
  let mergeChunks = [];
  let mergeBytes = 0;
  let mergeTimer = null;
  let mergeGeneration = 0;

  function setPlaybackActive(active) {
    const nextActive = Boolean(active);
    if (playbackActive.value === nextActive) return;
    playbackActive.value = nextActive;
    onPlaybackStateChange?.(nextActive);
  }

  function stopPlaybackAnalysis() {
    if (playbackAnalysisFrame !== null) cancelAnimationFrame(playbackAnalysisFrame);
    playbackAnalysisFrame = null;
    audioLevel.value = 0;
  }

  function samplePlaybackLevel() {
    playbackAnalysisFrame = null;
    if (!playbackActive.value || !playbackAnalyser || !playbackAnalysisSamples) return;
    playbackAnalyser.getFloatTimeDomainData(playbackAnalysisSamples);
    audioLevel.value = Math.min(1, float32Metrics(playbackAnalysisSamples).rms * 3.2);
    // Follow the audio device clock every rendered frame because server chunk timing can run ahead of playback.
    playbackAnalysisFrame = requestAnimationFrame(samplePlaybackLevel);
  }

  function startPlaybackAnalysis() {
    if (playbackAnalysisFrame !== null) return;
    playbackAnalysisFrame = requestAnimationFrame(samplePlaybackLevel);
  }

  async function preparePlayback() {
    if (!playbackContext) {
      // Create playback during a user gesture because browsers may block contexts created by later socket events.
      playbackContext = new AudioContext({ sampleRate: 24000 });
      playbackCursor = playbackContext.currentTime;
      playbackAnalyser = playbackContext.createAnalyser();
      playbackAnalyser.fftSize = 512;
      playbackAnalysisSamples = new Float32Array(playbackAnalyser.fftSize);
      // Route every source through one analyser so lip sync reflects the sound actually sent to the speakers.
      playbackAnalyser.connect(playbackContext.destination);
    }
    if (playbackContext.state === "suspended") await playbackContext.resume();
  }

  async function startCapture() {
    if (["starting", "recording"].includes(microphoneState.value)) return;
    microphoneState.value = "starting";
    qualityTracker.reset();
    inputLevel.value = 0;
    inputQuality.value = "good";
    try {
      captureStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const settings = captureStream.getAudioTracks?.()[0]?.getSettings?.() || {};
      autoGainState.value = "autoGainControl" in settings
        ? (settings.autoGainControl ? "enabled" : "disabled")
        : "unsupported";
      captureContext = new AudioContext();
      // Keep the worklet under the feature asset path so Vite development and production share one URL.
      await captureContext.audioWorklet.addModule("/digital-human/pcm-capture-worklet.js");
      const source = captureContext.createMediaStreamSource(captureStream);
      captureNode = new AudioWorkletNode(captureContext, "pcm-capture-processor");
      captureNode.port.onmessage = ({ data }) => {
        if (data?.type !== "pcm" || !(data.buffer instanceof ArrayBuffer)) return;
        const quality = qualityTracker.add(data.metrics);
        inputLevel.value = Math.min(1, quality.latestRms * 12);
        inputQuality.value = quality.inputQuality;
        onCaptureChunk?.(data.buffer, data.metrics);
      };
      source.connect(captureNode);
      // A silent gain keeps the worklet alive without feeding microphone audio to speakers.
      const silentGain = captureContext.createGain();
      silentGain.gain.value = 0;
      captureNode.connect(silentGain).connect(captureContext.destination);
      microphoneState.value = "recording";
      return true;
    } catch (error) {
      microphoneState.value = "denied";
      await stopCapture();
      throw error;
    }
  }

  async function stopCapture() {
    captureNode?.disconnect();
    captureNode = null;
    captureStream?.getTracks().forEach((track) => track.stop());
    captureStream = null;
    if (captureContext) await captureContext.close();
    captureContext = null;
    inputLevel.value = 0;
    if (microphoneState.value !== "denied") microphoneState.value = "idle";
  }

  function beginFinishing() {
    if (microphoneState.value === "recording") microphoneState.value = "finishing";
  }

  function clearMergeBuffer() {
    if (mergeTimer !== null) {
      clearTimeout(mergeTimer);
      mergeTimer = null;
    }
    mergeChunks = [];
    mergeBytes = 0;
    mergeGeneration += 1;
  }

  async function playPcmBuffer(arrayBuffer) {
    if (!arrayBuffer?.byteLength) return;
    await preparePlayback();
    const pcm = new Int16Array(arrayBuffer);
    const buffer = playbackContext.createBuffer(1, pcm.length, 24000);
    const channel = buffer.getChannelData(0);
    for (let index = 0; index < pcm.length; index += 1) channel[index] = pcm[index] / 32768;
    const source = playbackContext.createBufferSource();
    const sourceGeneration = playbackGeneration;
    source.buffer = buffer;
    source.connect(playbackAnalyser);
    const startAt = Math.max(playbackCursor, playbackContext.currentTime + 0.015);
    playbackCursor = startAt + buffer.duration;
    playbackSources.add(source);
    setPlaybackActive(true);
    startPlaybackAnalysis();
    source.onended = () => {
      // Ignore callbacks from a cancelled queue because a newer answer may already be playing.
      if (sourceGeneration !== playbackGeneration) return;
      playbackSources.delete(source);
      if (!playbackSources.size) {
        stopPlaybackAnalysis();
        setPlaybackActive(false);
      }
    };
    source.start(startAt);
  }

  async function flushMergedPlayback(expectedGeneration) {
    if (expectedGeneration !== mergeGeneration) return;
    mergeTimer = null;
    if (!mergeChunks.length) return;
    const total = mergeBytes;
    const merged = new Uint8Array(total);
    let offset = 0;
    for (const chunk of mergeChunks) {
      merged.set(new Uint8Array(chunk), offset);
      offset += chunk.byteLength;
    }
    mergeChunks = [];
    mergeBytes = 0;
    await playPcmBuffer(merged.buffer);
  }

  async function enqueuePlayback(arrayBuffer) {
    if (!arrayBuffer?.byteLength) return;
    await preparePlayback();
    mergeChunks.push(arrayBuffer);
    mergeBytes += arrayBuffer.byteLength;
    const generation = mergeGeneration;
    // 达到时长上限立即冲刷，否则在短窗内合并后续小块。
    if (mergeBytes >= PLAYBACK_MERGE_MAX_BYTES) {
      if (mergeTimer !== null) {
        clearTimeout(mergeTimer);
        mergeTimer = null;
      }
      await flushMergedPlayback(generation);
      return;
    }
    if (mergeTimer !== null) return;
    mergeTimer = setTimeout(() => {
      flushMergedPlayback(generation).catch(() => {
        // 合并失败时下一帧仍可继续收听，避免整条播放链路中断。
      });
    }, PLAYBACK_MERGE_WINDOW_MS);
  }

  function clearPlayback() {
    clearMergeBuffer();
    playbackGeneration += 1;
    stopPlaybackAnalysis();
    for (const source of playbackSources) {
      try {
        source.stop();
      } catch {
        // A source may already be ended; ignoring it keeps cancellation immediate.
      }
    }
    playbackSources.clear();
    playbackCursor = playbackContext?.currentTime || 0;
    audioLevel.value = 0;
    setPlaybackActive(false);
  }

  async function dispose() {
    await stopCapture();
    clearPlayback();
    if (playbackContext) await playbackContext.close();
    playbackContext = null;
    playbackAnalyser = null;
    playbackAnalysisSamples = null;
  }

  return {
    audioLevel,
    playbackActive,
    inputLevel,
    inputQuality,
    autoGainState,
    microphoneState,
    captureSnapshot: () => qualityTracker.snapshot(),
    preparePlayback,
    startCapture,
    beginFinishing,
    stopCapture,
    enqueuePlayback,
    clearPlayback,
    dispose,
  };
}
