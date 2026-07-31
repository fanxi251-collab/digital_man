export const AVATAR_STORAGE_KEY = "lingjing_digital_human_avatar";
export const DEFAULT_AVATAR_ID = "mao_pro";

function haruMotion(index, durationMs, options = {}) {
  return Object.freeze({
    group: "",
    index,
    durationMs,
    loopWhileActive: false,
    ...options,
  });
}

const HARU_SEMANTIC_MOTIONS = Object.freeze({
  idle: haruMotion(0, 0, { loopWhileActive: true }),
  nod: haruMotion(1, 2900),
  thinking: haruMotion(2, 2030, { loopWhileActive: true }),
  agreement: haruMotion(13, 2530),
  surprised_agreement: haruMotion(26, 4970),
  // Rotate one professional positive gesture per answer so ordinary explanations do not look repetitive.
  explanation: Object.freeze({
    variants: Object.freeze([
      haruMotion(7, 3930, { loopWhileActive: true }),
      haruMotion(22, 5030, { loopWhileActive: true }),
      haruMotion(7, 3930, { loopWhileActive: true }),
      haruMotion(23, 4000, { loopWhileActive: true }),
      haruMotion(21, 5000, { loopWhileActive: true }),
    ]),
  }),
  route: haruMotion(7, 3930, { loopWhileActive: true }),
  welcome: haruMotion(8, 4600),
  polite_acknowledgement: haruMotion(9, 4030),
  compliment_shy: haruMotion(10, 5530),
  complaint_apology: haruMotion(19, 8000),
  cute_agreement: haruMotion(13, 2530),
  service_apology: haruMotion(9, 4030),
  shy: haruMotion(17, 4500),
  mistake_shy: haruMotion(18, 3200),
  prolonged_apology: haruMotion(19, 8000),
  conflicted: haruMotion(20, 6030),
  joy: haruMotion(21, 5000),
  polite_smile: Object.freeze({
    variants: Object.freeze([
      haruMotion(22, 5030),
      haruMotion(23, 4000),
    ]),
  }),
  mild_surprise_smile: haruMotion(26, 4970),
  strong_surprise_smile: haruMotion(26, 4970),
});

const PROFILES = Object.freeze({
  mao_pro: Object.freeze({
    id: "mao_pro",
    label: "Haru Greeter",
    roleLabel: "女导游",
    modelUrl: "/digital-human/live2d/haru_greeter/haru_greeter_t05.model3.json",
    attribution: "Haru Greeter sample © Live2D Inc.",
    expressionMap: Object.freeze({}),
    idleMotion: Object.freeze({ group: "", index: 0 }),
    semanticMotions: HARU_SEMANTIC_MOTIONS,
    fit: Object.freeze({ scale: 1, yOffset: 0.04 }),
  }),
  chitose: Object.freeze({
    id: "chitose",
    label: "Chitose",
    roleLabel: "男导游",
    modelUrl: "/digital-human/live2d/chitose/chitose.model3.json",
    attribution: "Chitose sample © Live2D Inc.",
    expressionMap: Object.freeze({
      neutral: "Normal.exp3.json",
      joy: "Smile.exp3.json",
      apology: "Sad.exp3.json",
      surprise: "Surprised.exp3.json",
    }),
    fit: Object.freeze({ scale: 1, yOffset: 0.04 }),
  }),
});

export const AVATAR_IDS = Object.freeze(Object.keys(PROFILES));
export const AVATAR_PROFILES = Object.freeze(AVATAR_IDS.map((id) => PROFILES[id]));

export function normalizeAvatarId(avatarId) {
  const normalized = String(avatarId || "").trim();
  return Object.hasOwn(PROFILES, normalized) ? normalized : DEFAULT_AVATAR_ID;
}

export function resolveAvatarProfile(avatarId) {
  return PROFILES[normalizeAvatarId(avatarId)];
}

export function avatarExpression(avatarId, semanticExpression) {
  const profile = resolveAvatarProfile(avatarId);
  return profile.expressionMap[String(semanticExpression || "neutral")] || null;
}

export function loadAvatarPreference(storage = globalThis.localStorage) {
  try {
    return normalizeAvatarId(storage?.getItem?.(AVATAR_STORAGE_KEY));
  } catch {
    return DEFAULT_AVATAR_ID;
  }
}

export function saveAvatarPreference(storage = globalThis.localStorage, avatarId) {
  const normalized = normalizeAvatarId(avatarId);
  try {
    storage?.setItem?.(AVATAR_STORAGE_KEY, normalized);
  } catch {
    // Browser privacy modes may reject storage; the in-memory choice must remain usable.
  }
  return normalized;
}
