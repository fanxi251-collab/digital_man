function normalizeText(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/\s+/g, "")
    .replace(/[，。！？、；：,.!?;:（）()“”"'《》]/g, "");
}

function includesAny(text, phrases) {
  return phrases.some((phrase) => text.includes(phrase));
}

export const MOTION_INTENT_DEBOUNCE_MS = 300;

const APOLOGY_PHRASES = ["抱歉", "对不起", "不好意思", "遗憾"];
const LONG_APOLOGY_PHRASES = [
  "非常抱歉",
  "再次向您道歉",
  "给您带来不便",
  "确实是我的失误",
  "深表歉意",
];
const COMPLAINT_PHRASES = [
  "投诉",
  "抱怨",
  "不满意",
  "讲错",
  "说错",
  "错了",
  "怎么回事",
  "没有用",
  "没用",
  "骗人",
  "责怪",
];
const PRAISE_PHRASES = [
  "真专业",
  "真棒",
  "你真厉害",
  "你很厉害",
  "你真优秀",
  "你很优秀",
  "你好看",
  "你真漂亮",
  "你很漂亮",
  "你真可爱",
  "你很可爱",
  "喜欢你",
  "声音好听",
  "讲得好",
  "夸奖",
];
const MISTAKE_PHRASES = ["我的失误", "我说错", "我讲错", "回答有误", "刚才出错"];
const SHY_PHRASES = ["害羞", "不好意思了", "有些不好意思", "有点不好意思"];
const SERVICE_FAILURE_PHRASES = [
  "暂不可用",
  "服务失败",
  "加载失败",
  "语音失败",
  "路线失败",
  "请重新尝试",
  "稍后重试",
];
const STRONG_SURPRISE_PHRASES = ["难以置信", "竟然", "太惊讶", "非常惊喜", "令人震惊"];
const MILD_SURPRISE_PHRASES = ["原来", "有些意外", "有点意外", "略感惊讶", "没想到"];
const CONFLICT_PHRASES = [
  "各有优缺点",
  "需要权衡",
  "难以确定",
  "难以判断",
  "取决于您的选择",
  "取决于您的偏好",
  "比较纠结",
];
const AGREEMENT_PHRASES = ["您说得对", "确实如此", "完全赞同", "我赞同", "没错"];
const CUTE_AGREEMENT_PHRASES = ["对呀", "是呀", "挺有意思呢", "很有趣呢"];
const ACKNOWLEDGEMENT_PHRASES = ["我明白了", "已经记下", "记下您的反馈", "收到您的反馈", "请放心"];
const POLITE_SMILE_PHRASES = ["不客气", "祝您游览愉快", "希望对您有帮助", "很高兴为您服务"];
const JOY_PHRASES = ["欢迎回来", "特别开心", "非常开心", "见到大家", "太高兴了"];

export function resolveHaruMotionIntent({
  state = "idle",
  userText = "",
  assistantText = "",
  hasRouteSource = false,
} = {}) {
  const normalizedState = String(state || "idle");
  const user = normalizeText(userText);
  const assistant = normalizeText(assistantText);
  const combined = `${user}${assistant}`;

  if (normalizedState === "error") return "service_apology";
  if (normalizedState === "thinking") return "thinking";
  if (normalizedState !== "speaking") return "idle";
  if (hasRouteSource) return "route";

  if (includesAny(assistant, SERVICE_FAILURE_PHRASES)) return "service_apology";
  if (includesAny(assistant, LONG_APOLOGY_PHRASES)) return "prolonged_apology";
  if (
    includesAny(assistant, MISTAKE_PHRASES)
    && (includesAny(assistant, SHY_PHRASES) || includesAny(assistant, APOLOGY_PHRASES))
  ) {
    return "mistake_shy";
  }
  if (
    includesAny(user, COMPLAINT_PHRASES)
    && includesAny(assistant, APOLOGY_PHRASES)
  ) {
    return "complaint_apology";
  }
  if (includesAny(user, PRAISE_PHRASES)) return "compliment_shy";
  if (includesAny(assistant, SHY_PHRASES)) return "shy";
  if (includesAny(assistant, JOY_PHRASES)) return "joy";
  if (includesAny(combined, STRONG_SURPRISE_PHRASES)) return "strong_surprise_smile";
  if (includesAny(assistant, CONFLICT_PHRASES)) return "conflicted";
  if (
    includesAny(assistant, AGREEMENT_PHRASES)
    && includesAny(assistant, MILD_SURPRISE_PHRASES)
  ) {
    return "surprised_agreement";
  }
  if (includesAny(assistant, CUTE_AGREEMENT_PHRASES)) return "cute_agreement";
  if (includesAny(assistant, AGREEMENT_PHRASES)) return "agreement";
  if (/^(是的|对的|可以|没问题)$/.test(assistant)) return "nod";
  if (includesAny(assistant, ACKNOWLEDGEMENT_PHRASES)) return "polite_acknowledgement";
  if (includesAny(assistant, POLITE_SMILE_PHRASES)) return "polite_smile";
  if (includesAny(combined, MILD_SURPRISE_PHRASES)) return "mild_surprise_smile";
  if (includesAny(assistant, APOLOGY_PHRASES)) return "service_apology";
  return "explanation";
}

export function createMotionVariantRotator() {
  const nextIndices = new Map();

  return {
    pick(key, variants) {
      if (!Array.isArray(variants) || !variants.length) return null;
      const nextIndex = nextIndices.get(key) || 0;
      const selected = variants[nextIndex % variants.length];
      nextIndices.set(key, (nextIndex + 1) % variants.length);
      return selected;
    },
    reset() {
      nextIndices.clear();
    },
  };
}

export function createMotionIntentDebouncer(commit, options = {}) {
  const schedule = options.schedule || ((callback, delay) => globalThis.setTimeout(callback, delay));
  const cancel = options.cancel || ((handle) => globalThis.clearTimeout(handle));
  let timerHandle = null;
  let disposed = false;

  function clearPending() {
    if (timerHandle === null) return;
    cancel(timerHandle);
    timerHandle = null;
  }

  return {
    update(intent) {
      if (disposed) return;
      clearPending();
      timerHandle = schedule(() => {
        timerHandle = null;
        if (!disposed) commit(intent);
      }, MOTION_INTENT_DEBOUNCE_MS);
    },
    commitNow(intent) {
      if (disposed) return;
      clearPending();
      commit(intent);
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      clearPending();
    },
  };
}
