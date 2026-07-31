import assert from "node:assert/strict";
import test from "node:test";

import {
  MOTION_INTENT_DEBOUNCE_MS,
  createMotionIntentDebouncer,
  createMotionVariantRotator,
  resolveHaruMotionIntent,
} from "../src/features/digital-human/lib/live2dSemanticMotion.js";

test("Haru semantic motion gives system state and route evidence priority over wording", () => {
  assert.equal(resolveHaruMotionIntent({
    state: "error",
    userText: "路线怎么走",
    assistantText: "这条路线很清楚",
    hasRouteSource: true,
  }), "service_apology");
  assert.equal(resolveHaruMotionIntent({
    state: "thinking",
    assistantText: "欢迎您",
    hasRouteSource: true,
  }), "thinking");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "从五明桥到五智门怎么走",
    assistantText: "很抱歉让您久等，现在给您说明方向",
    hasRouteSource: true,
  }), "route");
});

test("Haru semantic motion distinguishes complaint, service and prolonged apology", () => {
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "你刚才讲错了，我很不满意",
    assistantText: "抱歉，我重新说明。",
  }), "complaint_apology");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "为什么路线还是打不开",
    assistantText: "非常抱歉，给您带来不便，确实是我的失误。",
  }), "prolonged_apology");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "非常抱歉，语音服务暂不可用，请重新尝试。",
  }), "service_apology");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "语音服务暂不可用，请重新尝试。",
  }), "service_apology");
  assert.equal(resolveHaruMotionIntent({
    state: "error",
    assistantText: "语音服务暂不可用，请重新尝试。",
  }), "service_apology");
});

test("Haru semantic motion chooses the most specific praise and shyness response", () => {
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "你讲得真专业，声音也很好听",
    assistantText: "谢谢您的夸奖。",
  }), "compliment_shy");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "你刚才说错了",
    assistantText: "这是我的失误，我有点不好意思。",
  }), "mistake_shy");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "您这么说，我都有些害羞了。",
  }), "shy");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "欢迎回来，见到大家我特别开心！",
  }), "joy");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    userText: "这里有可爱的动物吗",
    assistantText: "景区以文化建筑和自然景观为主。",
  }), "explanation");
});

test("Haru semantic motion separates nodding, agreement and surprised agreement", () => {
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "是的。",
  }), "nod");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "您说得对，这确实是游览重点。",
  }), "agreement");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "没错，原来您也发现这个细节了。",
  }), "surprised_agreement");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "对呀，这样安排还挺有意思呢。",
  }), "cute_agreement");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "好的，我明白了，也记下您的反馈。",
  }), "polite_acknowledgement");
});

test("Haru semantic motion separates surprise strength, uncertainty and polite smile", () => {
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "难以置信，这里竟然保存了这么完整的遗迹。",
  }), "strong_surprise_smile");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "原来如此，确实有些意外。",
  }), "mild_surprise_smile");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "两种方案各有优缺点，需要根据时间进行权衡。",
  }), "conflicted");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "游览时需要根据天气携带雨具。",
  }), "explanation");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "不客气，祝您游览愉快。",
  }), "polite_smile");
  assert.equal(resolveHaruMotionIntent({
    state: "speaking",
    assistantText: "灵山胜境主要包含多个文化景点。",
  }), "explanation");
  assert.equal(resolveHaruMotionIntent({ state: "idle" }), "idle");
});

test("equivalent motion variants rotate without immediate repetition", () => {
  const rotator = createMotionVariantRotator();

  assert.equal(rotator.pick("polite_smile", [22, 23]), 22);
  assert.equal(rotator.pick("polite_smile", [22, 23]), 23);
  assert.equal(rotator.pick("polite_smile", [22, 23]), 22);
  assert.equal(rotator.pick("single", [7]), 7);
  assert.equal(rotator.pick("empty", []), null);

  rotator.reset();
  assert.equal(rotator.pick("polite_smile", [22, 23]), 22);
});

test("streamed semantic motion waits 300ms while state transitions commit immediately", () => {
  const scheduled = [];
  const committed = [];
  const debouncer = createMotionIntentDebouncer((intent) => committed.push(intent), {
    schedule(callback, delay) {
      scheduled.push({ callback, delay, cancelled: false });
      return scheduled.length - 1;
    },
    cancel(handle) {
      scheduled[handle].cancelled = true;
    },
  });

  debouncer.update("explanation");
  debouncer.update("compliment_shy");
  assert.equal(MOTION_INTENT_DEBOUNCE_MS, 300);
  assert.equal(scheduled[0].cancelled, true);
  assert.equal(scheduled[1].delay, 300);
  assert.deepEqual(committed, []);

  scheduled[1].callback();
  assert.deepEqual(committed, ["compliment_shy"]);

  debouncer.update("polite_smile");
  debouncer.commitNow("thinking");
  assert.equal(scheduled[2].cancelled, true);
  assert.deepEqual(committed, ["compliment_shy", "thinking"]);
  debouncer.dispose();
});
