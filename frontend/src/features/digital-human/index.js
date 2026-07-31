export { default as DigitalHumanStage } from "./components/DigitalHumanStage.vue";
export { default as DigitalHumanAvatarSelector } from "./components/DigitalHumanAvatarSelector.vue";
export { default as DigitalHumanAnswerPanel } from "./components/DigitalHumanAnswerPanel.vue";
export { default as DigitalHumanVoiceControls } from "./components/DigitalHumanVoiceControls.vue";
export { default as TranscriptConfirmation } from "./components/TranscriptConfirmation.vue";
export { default as DigitalHumanTourMap } from "../guided-tour/components/DigitalHumanTourMap.vue";
export { createGuidedTour } from "../guided-tour/composables/useGuidedTour.js";
export { usePcmAudio } from "./composables/usePcmAudio.js";
export {
  TAIL_PROTECTION_MS,
  createCaptureQualityTracker,
  createTailProtection,
} from "./lib/audioCaptureQuality.js";
export { float32Metrics, float32ToInt16, pcmRms } from "./lib/pcmAudio.js";
export {
  AVATAR_IDS,
  AVATAR_PROFILES,
  DEFAULT_AVATAR_ID,
  avatarExpression,
  loadAvatarPreference,
  normalizeAvatarId,
  resolveAvatarProfile,
  saveAvatarPreference,
} from "./lib/live2dCharacters.js";
export {
  EXPRESSION_DEBOUNCE_MS,
  createExpressionDebouncer,
  resolveLive2DExpression,
} from "./lib/live2dExpression.js";
export {
  LIP_SYNC_ATTACK_MS,
  LIP_SYNC_RELEASE_MS,
  applyLipSyncValue,
  createMissingLipSyncWarning,
  live2DMouthTarget,
  resolveLipSyncIds,
  smoothLipSyncValue,
} from "./lib/live2dMotion.js";
export {
  MOTION_INTENT_DEBOUNCE_MS,
  createMotionIntentDebouncer,
  createMotionVariantRotator,
  resolveHaruMotionIntent,
} from "./lib/live2dSemanticMotion.js";
