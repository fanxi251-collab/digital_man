import { ref } from "vue";

import { narrationRequest } from "../lib/narrationPolicy.js";

export function createScenicNarration(options = {}) {
  const fetcher = options.fetcher || globalThis.fetch?.bind(globalThis);
  const audioFactory = options.audioFactory || ((url) => new Audio(url));
  const createObjectURL = options.createObjectURL || ((blob) => URL.createObjectURL(blob));
  const revokeObjectURL = options.revokeObjectURL || ((url) => URL.revokeObjectURL(url));
  const title = ref("");
  const text = ref("");
  const state = ref("idle");
  const source = ref("text");
  const audioLevel = ref(0);
  const requiresManualPlay = ref(false);
  const defaultMonitor = createBrowserLevelMonitorFactory(audioLevel);
  const levelMonitorFactory = options.levelMonitorFactory || defaultMonitor.create;
  let activeAudio = null;
  let activeMonitor = null;
  let activeObjectUrl = "";
  let blockedObjectUrl = "";
  let finishActivePlayback = null;
  let disposed = false;

  async function prepare() {
    await defaultMonitor.prepare();
  }

  async function play(stop) {
    stopPlayback("replaced");
    if (disposed) return { status: "disposed" };
    title.value = String(stop?.attraction_name || stop?.name || "景点讲解").trim();
    text.value = String(stop?.narration_text || stop?.summary || "").trim();
    state.value = "loading";
    source.value = "text";
    requiresManualPlay.value = false;
    const request = narrationRequest(stop);

    if (request.localAudioUrl) {
      const local = await fetchAndPlay(request.localAudioUrl, undefined, "local");
      if (local.status === "complete" || local.status === "blocked") return local;
    }
    if (request.onlineUrl) {
      const online = await fetchAndPlay(request.onlineUrl, { method: "POST" }, "online");
      if (online.status === "complete" || online.status === "blocked") return online;
    }

    state.value = "complete";
    source.value = "text";
    audioLevel.value = 0;
    return { status: "text_only" };
  }

  async function fetchAndPlay(url, fetchOptions, nextSource) {
    if (!fetcher) return { status: "error" };
    try {
      const response = await fetcher(url, fetchOptions);
      if (!response?.ok) return { status: "error" };
      const blob = await response.blob();
      const objectUrl = createObjectURL(blob);
      activeObjectUrl = objectUrl;
      source.value = nextSource;
      const result = await playObjectUrl(objectUrl);
      if (result.status === "blocked") {
        blockedObjectUrl = objectUrl;
        activeObjectUrl = "";
        return result;
      }
      releaseObjectUrl(objectUrl);
      activeObjectUrl = "";
      return result;
    } catch {
      if (activeObjectUrl) releaseObjectUrl(activeObjectUrl);
      activeObjectUrl = "";
      return { status: "error" };
    }
  }

  async function playObjectUrl(objectUrl) {
    cleanupAudio();
    activeAudio = audioFactory(objectUrl);
    activeMonitor = levelMonitorFactory(activeAudio, (level) => {
      audioLevel.value = Math.max(0, Math.min(1, Number(level) || 0));
    });
    const outcome = new Promise((resolve) => {
      finishActivePlayback = resolve;
      activeAudio.addEventListener("ended", () => resolve({ status: "complete" }), { once: true });
      activeAudio.addEventListener("error", () => resolve({ status: "error" }), { once: true });
    });
    state.value = "playing";
    activeMonitor?.start?.();
    try {
      await activeAudio.play();
    } catch (error) {
      if (error?.name === "NotAllowedError") {
        cleanupAudio();
        state.value = "blocked";
        requiresManualPlay.value = true;
        return { status: "blocked" };
      }
      cleanupAudio();
      return { status: "error" };
    }
    const result = await outcome;
    cleanupAudio();
    if (result.status === "complete") {
      state.value = "complete";
      requiresManualPlay.value = false;
    }
    return result;
  }

  async function playManually() {
    if (!blockedObjectUrl || disposed) return { status: "unavailable" };
    const objectUrl = blockedObjectUrl;
    blockedObjectUrl = "";
    requiresManualPlay.value = false;
    const result = await playObjectUrl(objectUrl);
    if (result.status !== "blocked") releaseObjectUrl(objectUrl);
    else blockedObjectUrl = objectUrl;
    return result;
  }

  function stopPlayback(reason = "user") {
    finishActivePlayback?.({ status: "interrupted", reason });
    cleanupAudio();
    if (activeObjectUrl) releaseObjectUrl(activeObjectUrl);
    if (blockedObjectUrl) releaseObjectUrl(blockedObjectUrl);
    activeObjectUrl = "";
    blockedObjectUrl = "";
    requiresManualPlay.value = false;
    audioLevel.value = 0;
    if (state.value !== "idle") state.value = "idle";
  }

  function cleanupAudio() {
    if (activeAudio) {
      activeAudio.pause?.();
      try { activeAudio.currentTime = 0; } catch { /* Some media doubles expose readonly time. */ }
    }
    activeMonitor?.stop?.();
    activeMonitor?.dispose?.();
    activeMonitor = null;
    activeAudio = null;
    finishActivePlayback = null;
    audioLevel.value = 0;
  }

  function releaseObjectUrl(url) {
    if (url) revokeObjectURL(url);
  }

  function dispose() {
    if (disposed) return;
    stopPlayback("dispose");
    disposed = true;
    defaultMonitor.dispose();
  }

  return {
    title,
    text,
    state,
    source,
    audioLevel,
    requiresManualPlay,
    prepare,
    play,
    playManually,
    stop: stopPlayback,
    dispose,
  };
}

function createBrowserLevelMonitorFactory(audioLevel) {
  let context = null;

  async function prepare() {
    const AudioContextClass = globalThis.AudioContext || globalThis.webkitAudioContext;
    if (!AudioContextClass) return;
    context ||= new AudioContextClass();
    if (context.state === "suspended") await context.resume();
  }

  function create(audio) {
    if (!context?.createMediaElementSource) return noOpMonitor();
    const analyser = context.createAnalyser();
    const samples = new Uint8Array(analyser.fftSize);
    const mediaSource = context.createMediaElementSource(audio);
    mediaSource.connect(analyser);
    analyser.connect(context.destination);
    let frameId = null;

    function sample() {
      analyser.getByteTimeDomainData(samples);
      let energy = 0;
      for (const value of samples) energy += ((value - 128) / 128) ** 2;
      audioLevel.value = Math.min(1, Math.sqrt(energy / samples.length) * 3.2);
      frameId = requestAnimationFrame(sample);
    }
    return {
      start() { if (frameId === null) frameId = requestAnimationFrame(sample); },
      stop() {
        if (frameId !== null) cancelAnimationFrame(frameId);
        frameId = null;
        audioLevel.value = 0;
      },
      dispose() {
        this.stop();
        mediaSource.disconnect();
        analyser.disconnect();
      },
    };
  }

  function dispose() {
    context?.close?.();
    context = null;
    audioLevel.value = 0;
  }
  return { prepare, create, dispose };
}

function noOpMonitor() {
  return { start() {}, stop() {}, dispose() {} };
}
