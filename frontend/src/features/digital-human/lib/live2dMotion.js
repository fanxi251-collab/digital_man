import { createMotionVariantRotator } from "./live2dSemanticMotion.js";

export const LIP_SYNC_ATTACK_MS = 60;
export const LIP_SYNC_RELEASE_MS = 120;
const FORCE_MOTION_PRIORITY = 3;

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

export function live2DMouthTarget(state, audioLevel) {
  if (state !== "speaking") return 0;
  return clamp(Number(audioLevel || 0) * 1.3, 0, 1);
}

export function smoothLipSyncValue(current, target, deltaMs) {
  const safeCurrent = clamp(Number(current || 0), 0, 1);
  const safeTarget = clamp(Number(target || 0), 0, 1);
  const timeConstant = safeTarget > safeCurrent
    ? LIP_SYNC_ATTACK_MS
    : LIP_SYNC_RELEASE_MS;
  const alpha = 1 - Math.exp(-Math.max(0, Number(deltaMs || 0)) / timeConstant);
  return safeCurrent + ((safeTarget - safeCurrent) * alpha);
}

export function resolveLipSyncIds(internalModel) {
  const motionManagerIds = internalModel?.motionManager?.lipSyncIds;
  const legacyIds = internalModel?.lipSyncIds;
  const primaryIds = Array.isArray(motionManagerIds)
    ? [...new Set(motionManagerIds.filter(Boolean))]
    : [];
  if (primaryIds.length) return primaryIds;
  return Array.isArray(legacyIds) ? [...new Set(legacyIds.filter(Boolean))] : [];
}

export function createMissingLipSyncWarning(warn = (message) => console.warn(message)) {
  let warned = false;
  return (internalModel) => {
    if (resolveLipSyncIds(internalModel).length || warned) return false;
    warned = true;
    // Warn once because silent lip-sync failures otherwise look like an animation limitation to operators.
    warn("Live2D 模型未声明可用的口型参数，语音将继续播放但嘴型不会变化。");
    return true;
  };
}

export async function startProfileIdleMotion(
  model,
  profile,
  warn = (message, error) => console.warn(message, error),
) {
  const motion = profile?.idleMotion;
  if (
    typeof model?.motion !== "function"
    || typeof motion?.group !== "string"
    || !Number.isInteger(motion?.index)
  ) {
    return false;
  }

  try {
    await model.motion(motion.group, motion.index);
    return true;
  } catch (error) {
    // An optional idle clip must not disable speech, because voice and lip sync are the primary interaction.
    warn("Live2D idle motion failed; continuing with the loaded model.", error);
    return false;
  }
}

export async function initializeProfileIdleState(
  model,
  profile,
  warn = (message, error) => console.warn(message, error),
) {
  const motion = profile?.idleMotion;
  if (
    typeof model?.motion !== "function"
    || typeof motion?.group !== "string"
    || !Number.isInteger(motion?.index)
  ) {
    return false;
  }

  const internalModel = model?.internalModel;
  if (typeof internalModel?.pose?.reset === "function" && internalModel.coreModel) {
    // Reset Pose first so the motion captures the intended arms instead of fading from the MOC default.
    internalModel.pose.reset(internalModel.coreModel);
  }
  return startProfileIdleMotion(model, profile, warn);
}

export function createExclusiveMotionController(model, profile, options = {}) {
  const schedule = options.schedule || ((callback, delay) => globalThis.setTimeout(callback, delay));
  const cancel = options.cancel || ((handle) => globalThis.clearTimeout(handle));
  const warn = options.warn || ((message, error) => console.warn(message, error));
  const rotator = options.rotator || createMotionVariantRotator();
  let generation = 0;
  let timerHandle = null;
  let currentMotionIdentity = "";
  let disposed = false;

  function clearTimer() {
    if (timerHandle === null) return;
    cancel(timerHandle);
    timerHandle = null;
  }

  function resolveDescriptor(intent) {
    const configured = profile?.semanticMotions?.[intent];
    if (!configured) return null;
    if (Array.isArray(configured.variants)) {
      return rotator.pick(intent, configured.variants);
    }
    return configured;
  }

  async function playIntent(intent, fallbackIntent = "idle") {
    if (disposed) return false;
    const descriptor = resolveDescriptor(intent);
    if (
      !descriptor
      || typeof descriptor.group !== "string"
      || !Number.isInteger(descriptor.index)
      || typeof model?.motion !== "function"
    ) {
      return false;
    }

    const identity = `${descriptor.group}:${descriptor.index}`;
    if (identity === currentMotionIdentity) return true;

    generation += 1;
    const playGeneration = generation;
    clearTimer();

    try {
      const started = await model.motion(
        descriptor.group,
        descriptor.index,
        FORCE_MOTION_PRIORITY,
      );
      if (disposed || playGeneration !== generation || started === false) return false;
      currentMotionIdentity = identity;

      if (!descriptor.loopWhileActive && Number(descriptor.durationMs) > 0) {
        timerHandle = schedule(async () => {
          timerHandle = null;
          if (disposed || playGeneration !== generation) return;
          currentMotionIdentity = "";
          await playIntent(fallbackIntent, "idle");
        }, descriptor.durationMs);
      }
      return true;
    } catch (error) {
      // Optional body gestures must never break the primary speech, subtitle, or lip-sync path.
      warn(`Live2D semantic motion "${intent}" failed.`, error);
      return false;
    }
  }

  return {
    setIntent(intent, fallbackIntent = "idle") {
      return playIntent(intent, fallbackIntent);
    },
    playEntryMotion() {
      return playIntent("welcome", "idle");
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      generation += 1;
      clearTimer();
      currentMotionIdentity = "";
      rotator.reset();
    },
  };
}

export function createFirstFrameReveal(internalModel, canvas, options = {}) {
  const schedule = options.schedule
    || ((callback) => globalThis.requestAnimationFrame(callback));
  const cancelScheduled = options.cancelScheduled
    || ((handle) => globalThis.cancelAnimationFrame(handle));
  let resolveRevealed;
  const revealed = new Promise((resolve) => {
    resolveRevealed = resolve;
  });
  let motionReady = false;
  let cancelled = false;
  let settled = false;
  let scheduledHandle = null;

  function settle(value) {
    if (settled) return;
    settled = true;
    resolveRevealed(value);
  }

  function handleModelUpdate() {
    if (!motionReady || cancelled) return;
    internalModel.off("afterMotionUpdate", handleModelUpdate);
    scheduledHandle = schedule(() => {
      scheduledHandle = null;
      if (cancelled) {
        settle(false);
        return;
      }
      canvas.style.visibility = "";
      settle(true);
    });
  }

  if (!canvas?.style || !internalModel?.on || !internalModel?.off) {
    settle(false);
    return {
      revealed,
      markMotionReady() {},
      cancel() {},
    };
  }

  // Hide only the canvas while Pixi keeps rendering, so the first visible frame already contains the idle motion.
  canvas.style.visibility = "hidden";
  internalModel.on("afterMotionUpdate", handleModelUpdate);

  return {
    revealed,
    markMotionReady() {
      motionReady = true;
    },
    cancel() {
      if (cancelled) return;
      cancelled = true;
      internalModel.off("afterMotionUpdate", handleModelUpdate);
      if (scheduledHandle !== null) cancelScheduled(scheduledHandle);
      settle(false);
    },
  };
}

export function applyLipSyncValue(internalModel, value) {
  const coreModel = internalModel?.coreModel;
  if (!coreModel?.setParameterValueById) return;
  // Read IDs from the renderer's real motion manager so model-specific mouth parameters are never hard-coded.
  for (const parameterId of resolveLipSyncIds(internalModel)) {
    coreModel.setParameterValueById(parameterId, clamp(Number(value || 0), 0, 1));
  }
}
