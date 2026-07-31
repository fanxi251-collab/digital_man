import assert from "node:assert/strict";
import test from "node:test";

import * as live2dMotion from "../src/features/digital-human/lib/live2dMotion.js";
import {
  LIP_SYNC_ATTACK_MS,
  LIP_SYNC_RELEASE_MS,
  applyLipSyncValue,
  createExclusiveMotionController,
  live2DMouthTarget,
  resolveLipSyncIds,
  smoothLipSyncValue,
} from "../src/features/digital-human/lib/live2dMotion.js";
import {
  EXPRESSION_DEBOUNCE_MS,
  createExpressionDebouncer,
  resolveLive2DExpression,
} from "../src/features/digital-human/lib/live2dExpression.js";
import { resolveAvatarProfile } from "../src/features/digital-human/lib/live2dCharacters.js";

test("Live2D mouth opens only while speaking and clamps amplified audio", () => {
  assert.equal(live2DMouthTarget("idle", 0.8), 0);
  assert.equal(live2DMouthTarget("speaking", -1), 0);
  assert.equal(live2DMouthTarget("speaking", 0.5), 0.65);
  assert.equal(live2DMouthTarget("speaking", 1), 1);
});

test("Live2D mouth uses a faster attack than release", () => {
  const opened = smoothLipSyncValue(0, 1, 60);
  const remainingAfterRelease = smoothLipSyncValue(1, 0, 60);

  assert.equal(LIP_SYNC_ATTACK_MS, 60);
  assert.equal(LIP_SYNC_RELEASE_MS, 120);
  assert.ok(opened > 0.63 && opened < 0.64);
  assert.ok(remainingAfterRelease > 0.6 && remainingAfterRelease < 0.61);
});

test("Live2D mouth writes every model-provided lip sync parameter", () => {
  const writes = [];
  const internalModel = {
    motionManager: {
      lipSyncIds: ["ParamA", "ParamMouthOpenY"],
    },
    coreModel: {
      setParameterValueById(id, value) {
        writes.push([id, value]);
      },
    },
  };

  applyLipSyncValue(internalModel, 0.72);

  assert.deepEqual(writes, [
    ["ParamA", 0.72],
    ["ParamMouthOpenY", 0.72],
  ]);
});

test("Live2D lip sync IDs prefer the real motion manager and safely fall back", () => {
  assert.deepEqual(resolveLipSyncIds({
    motionManager: { lipSyncIds: ["", "ParamA", "ParamA", null] },
    lipSyncIds: ["ParamMouthOpenY"],
  }), ["ParamA"]);
  assert.deepEqual(resolveLipSyncIds({
    motionManager: { lipSyncIds: ["", null] },
    lipSyncIds: ["ParamMouthOpenY", "ParamMouthOpenY"],
  }), ["ParamMouthOpenY"]);
  assert.deepEqual(resolveLipSyncIds({
    motionManager: { lipSyncIds: "ParamA" },
    lipSyncIds: ["ParamLegacy"],
  }), ["ParamLegacy"]);
  assert.deepEqual(resolveLipSyncIds({}), []);
});

test("Live2D missing lip sync parameters warn only once per renderer", () => {
  assert.equal(typeof live2dMotion.createMissingLipSyncWarning, "function");
  const warnings = [];
  const warnIfMissing = live2dMotion.createMissingLipSyncWarning((message) => {
    warnings.push(message);
  });

  assert.equal(warnIfMissing({ motionManager: { lipSyncIds: ["ParamA"] } }), false);
  assert.equal(warnIfMissing({ motionManager: { lipSyncIds: [] } }), true);
  assert.equal(warnIfMissing({ motionManager: { lipSyncIds: [] } }), false);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /Live2D.*口型参数/);
});

test("Live2D starts the female profile idle motion and safely skips unconfigured profiles", async () => {
  assert.equal(typeof live2dMotion.startProfileIdleMotion, "function");
  const calls = [];
  const model = {
    async motion(group, index) {
      calls.push([group, index]);
    },
  };

  assert.equal(await live2dMotion.startProfileIdleMotion(model, {
    idleMotion: { group: "", index: 0 },
  }), true);
  assert.deepEqual(calls, [["", 0]]);
  assert.equal(await live2dMotion.startProfileIdleMotion(model, {}), false);

  const warnings = [];
  assert.equal(await live2dMotion.startProfileIdleMotion({
    async motion() {
      throw new Error("motion unavailable");
    },
  }, {
    idleMotion: { group: "", index: 0 },
  }, (message) => warnings.push(message)), false);
  assert.equal(warnings.length, 1);
  assert.match(warnings[0], /idle motion/);
});

test("Live2D resets the pose before the idle motion captures its fade origin", async () => {
  assert.equal(typeof live2dMotion.initializeProfileIdleState, "function");
  const calls = [];
  const coreModel = {};
  const model = {
    internalModel: {
      coreModel,
      pose: {
        reset(receivedCoreModel) {
          assert.equal(receivedCoreModel, coreModel);
          calls.push("pose.reset");
        },
      },
    },
    async motion(group, index) {
      assert.equal(group, "");
      assert.equal(index, 0);
      calls.push("motion");
    },
  };

  assert.equal(await live2dMotion.initializeProfileIdleState(model, {
    idleMotion: { group: "", index: 0 },
  }), true);
  assert.deepEqual(calls, ["pose.reset", "motion"]);
});

test("exclusive Live2D motion controller preempts old motion and ignores stale fallback", async () => {
  const calls = [];
  const scheduled = [];
  const cancelled = [];
  const model = {
    async motion(group, index, priority) {
      calls.push([group, index, priority]);
      return true;
    },
  };
  const profile = {
    semanticMotions: {
      idle: { group: "", index: 0, loopWhileActive: true },
      welcome: { group: "", index: 8, durationMs: 4600 },
      thinking: { group: "", index: 2, loopWhileActive: true },
    },
  };
  const controller = createExclusiveMotionController(model, profile, {
    schedule(callback, delay) {
      scheduled.push({ callback, delay });
      return scheduled.length - 1;
    },
    cancel(handle) {
      cancelled.push(handle);
    },
  });

  await controller.setIntent("welcome", "idle");
  assert.deepEqual(calls, [["", 8, 3]]);
  assert.equal(scheduled[0].delay, 4600);

  await controller.setIntent("thinking", "idle");
  assert.deepEqual(calls, [["", 8, 3], ["", 2, 3]]);
  assert.deepEqual(cancelled, [0]);

  await scheduled[0].callback();
  assert.deepEqual(calls, [["", 8, 3], ["", 2, 3]]);
});

test("exclusive Live2D motion controller avoids restarting aliases of the same loop", async () => {
  const calls = [];
  const model = {
    async motion(group, index, priority) {
      calls.push([group, index, priority]);
      return true;
    },
  };
  const controller = createExclusiveMotionController(model, {
    semanticMotions: {
      idle: { group: "", index: 0, loopWhileActive: true },
      explanation: { group: "", index: 7, loopWhileActive: true },
      route: { group: "", index: 7, loopWhileActive: true },
    },
  });

  await controller.setIntent("explanation", "idle");
  await controller.setIntent("route", "idle");

  assert.deepEqual(calls, [["", 7, 3]]);
});

test("exclusive Live2D motion controller returns one-shot gestures to fallback", async () => {
  const calls = [];
  const scheduled = [];
  const model = {
    async motion(group, index, priority) {
      calls.push([group, index, priority]);
      return true;
    },
  };
  const controller = createExclusiveMotionController(model, {
    semanticMotions: {
      idle: { group: "", index: 0, loopWhileActive: true },
      compliment_shy: { group: "", index: 10, durationMs: 5530 },
    },
  }, {
    schedule(callback, delay) {
      scheduled.push({ callback, delay });
      return scheduled.length - 1;
    },
    cancel() {},
  });

  await controller.setIntent("compliment_shy", "idle");
  assert.equal(scheduled[0].delay, 5530);
  await scheduled[0].callback();

  assert.deepEqual(calls, [["", 10, 3], ["", 0, 3]]);
});

test("exclusive Live2D motion controller rotates equivalent gestures and dispose blocks old timers", async () => {
  const calls = [];
  const scheduled = [];
  const cancelled = [];
  const model = {
    async motion(group, index, priority) {
      calls.push([group, index, priority]);
      return true;
    },
  };
  const controller = createExclusiveMotionController(model, {
    semanticMotions: {
      idle: { group: "", index: 0, loopWhileActive: true },
      polite_smile: {
        variants: [
          { group: "", index: 22, durationMs: 5030 },
          { group: "", index: 23, durationMs: 4000 },
        ],
      },
    },
  }, {
    schedule(callback, delay) {
      scheduled.push({ callback, delay });
      return scheduled.length - 1;
    },
    cancel(handle) {
      cancelled.push(handle);
    },
  });

  await controller.setIntent("polite_smile", "idle");
  await scheduled[0].callback();
  await controller.setIntent("polite_smile", "idle");
  assert.deepEqual(calls.slice(0, 3), [["", 22, 3], ["", 0, 3], ["", 23, 3]]);

  controller.dispose();
  await scheduled[1].callback();
  assert.deepEqual(calls.slice(0, 3), [["", 22, 3], ["", 0, 3], ["", 23, 3]]);
  assert.ok(cancelled.length >= 1);
});

test("general explanation rotates one retained gesture per turn while route stays directional", async () => {
  const calls = [];
  const model = {
    async motion(group, index, priority) {
      calls.push([group, index, priority]);
      return true;
    },
  };
  const controller = createExclusiveMotionController(
    model,
    resolveAvatarProfile("mao_pro"),
  );

  for (let turn = 0; turn < 5; turn += 1) {
    await controller.setIntent("explanation", "idle");
    if (turn < 4) await controller.setIntent("idle", "idle");
  }
  await controller.setIntent("idle", "idle");
  await controller.setIntent("route", "idle");

  assert.deepEqual(
    calls.map(([, index]) => index),
    [7, 0, 22, 0, 7, 0, 23, 0, 21, 0, 7],
  );
});

test("Live2D first frame stays hidden until the configured motion updates the model", async () => {
  assert.equal(typeof live2dMotion.createFirstFrameReveal, "function");
  const listeners = new Map();
  const internalModel = {
    on(event, handler) { listeners.set(event, handler); },
    off(event, handler) {
      if (listeners.get(event) === handler) listeners.delete(event);
    },
  };
  const canvas = { style: { visibility: "" } };
  const scheduled = [];
  const gate = live2dMotion.createFirstFrameReveal(internalModel, canvas, {
    schedule(callback) {
      scheduled.push(callback);
      return scheduled.length - 1;
    },
    cancelScheduled() {},
  });

  assert.equal(canvas.style.visibility, "hidden");
  listeners.get("afterMotionUpdate")();
  assert.equal(scheduled.length, 0);

  gate.markMotionReady();
  listeners.get("afterMotionUpdate")();
  assert.equal(canvas.style.visibility, "hidden");
  assert.equal(scheduled.length, 1);

  scheduled[0]();
  assert.equal(await gate.revealed, true);
  assert.equal(canvas.style.visibility, "");
  assert.equal(listeners.has("afterMotionUpdate"), false);
});

test("Live2D first-frame reveal cancellation ignores a delayed animation frame", async () => {
  assert.equal(typeof live2dMotion.createFirstFrameReveal, "function");
  let updateHandler;
  const internalModel = {
    on(_event, handler) { updateHandler = handler; },
    off(_event, handler) {
      if (updateHandler === handler) updateHandler = null;
    },
  };
  const canvas = { style: { visibility: "" } };
  const scheduled = [];
  const cancelled = [];
  const gate = live2dMotion.createFirstFrameReveal(internalModel, canvas, {
    schedule(callback) {
      scheduled.push(callback);
      return 7;
    },
    cancelScheduled(handle) { cancelled.push(handle); },
  });

  gate.markMotionReady();
  updateHandler();
  gate.cancel();
  scheduled[0]();

  assert.equal(await gate.revealed, false);
  assert.deepEqual(cancelled, [7]);
  assert.equal(canvas.style.visibility, "hidden");
  assert.equal(updateHandler, null);
});

test("Live2D lip sync writes clamp values to the model parameter range", () => {
  const writes = [];
  const internalModel = {
    motionManager: { lipSyncIds: ["ParamA"] },
    coreModel: {
      setParameterValueById(id, value) { writes.push([id, value]); },
    },
  };

  applyLipSyncValue(internalModel, -0.5);
  applyLipSyncValue(internalModel, 1.5);

  assert.deepEqual(writes, [["ParamA", 0], ["ParamA", 1]]);
});

test("Live2D expression uses professional categories and conflict priority", () => {
  assert.equal(resolveLive2DExpression({ state: "idle", assistantText: "欢迎您" }), "neutral");
  assert.equal(resolveLive2DExpression({ state: "speaking", assistantText: "欢迎体验精彩景区" }), "joy");
  assert.equal(resolveLive2DExpression({ state: "speaking", assistantText: "这里非常壮观，是首次开放" }), "surprise");
  assert.equal(resolveLive2DExpression({ state: "speaking", assistantText: "很抱歉，特别活动暂不可用" }), "apology");
  assert.equal(resolveLive2DExpression({ state: "error", assistantText: "欢迎" }), "apology");
  assert.equal(resolveLive2DExpression({ state: "speaking", assistantText: "普通路线说明" }), "neutral");
});

test("Live2D expression waits 300ms and reset returns to neutral immediately", () => {
  const scheduled = [];
  const committed = [];
  const debouncer = createExpressionDebouncer((expression) => committed.push(expression), {
    schedule(callback, delay) {
      scheduled.push({ callback, delay, cancelled: false });
      return scheduled.length - 1;
    },
    cancel(handle) {
      scheduled[handle].cancelled = true;
    },
  });

  debouncer.update("joy");
  assert.equal(EXPRESSION_DEBOUNCE_MS, 300);
  assert.equal(scheduled[0].delay, 300);
  assert.deepEqual(committed, []);

  debouncer.reset();
  assert.equal(scheduled[0].cancelled, true);
  assert.deepEqual(committed, ["neutral"]);
});
