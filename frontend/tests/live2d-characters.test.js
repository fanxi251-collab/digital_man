import assert from "node:assert/strict";
import test from "node:test";

import {
  AVATAR_IDS,
  DEFAULT_AVATAR_ID,
  avatarExpression,
  loadAvatarPreference,
  resolveAvatarProfile,
  saveAvatarPreference,
} from "../src/features/digital-human/lib/live2dCharacters.js";

test("digital human registry exposes Haru Greeter through the compatible female guide ID", () => {
  assert.deepEqual(AVATAR_IDS, ["mao_pro", "chitose"]);
  assert.equal(DEFAULT_AVATAR_ID, "mao_pro");

  const female = resolveAvatarProfile("mao_pro");
  const male = resolveAvatarProfile("chitose");
  assert.equal(female.label, "Haru Greeter");
  assert.equal(
    female.modelUrl,
    "/digital-human/live2d/haru_greeter/haru_greeter_t05.model3.json",
  );
  assert.deepEqual(female.idleMotion, { group: "", index: 0 });
  assert.equal(female.semanticMotions.thinking.index, 2);
  assert.equal(female.semanticMotions.route.index, 7);
  assert.equal(female.semanticMotions.welcome.index, 8);
  assert.deepEqual(
    female.semanticMotions.explanation.variants.map((motion) => motion.index),
    [7, 22, 7, 23, 21],
  );
  assert.equal(
    female.semanticMotions.explanation.variants.every((motion) => motion.loopWhileActive),
    true,
  );
  assert.equal(female.semanticMotions.agreement.index, 13);
  assert.equal(female.semanticMotions.surprised_agreement.index, 26);
  assert.equal(female.semanticMotions.complaint_apology.index, 19);
  assert.equal(female.semanticMotions.service_apology.index, 9);
  assert.equal(female.semanticMotions.mild_surprise_smile.index, 26);
  assert.deepEqual(
    female.semanticMotions.polite_smile.variants.map((motion) => motion.index),
    [22, 23],
  );
  const configuredMotionIndices = Object.values(female.semanticMotions)
    .flatMap((motion) => motion.variants || [motion])
    .map((motion) => motion.index);
  for (const excludedIndex of [3, 4, 5, 6, 11, 12, 14, 15, 16, 24, 25]) {
    assert.equal(configuredMotionIndices.includes(excludedIndex), false);
  }
  assert.equal(male.modelUrl, "/digital-human/live2d/chitose/chitose.model3.json");
  assert.equal(male.semanticMotions, undefined);
  assert.equal(male.roleLabel, "男导游");
  assert.equal(resolveAvatarProfile("unknown").id, DEFAULT_AVATAR_ID);
});

test("semantic expressions safely skip Haru because the runtime has no expression files", () => {
  assert.equal(avatarExpression("mao_pro", "neutral"), null);
  assert.equal(avatarExpression("mao_pro", "joy"), null);
  assert.equal(avatarExpression("mao_pro", "apology"), null);
  assert.equal(avatarExpression("mao_pro", "surprise"), null);
  assert.equal(avatarExpression("chitose", "neutral"), "Normal.exp3.json");
  assert.equal(avatarExpression("chitose", "apology"), "Sad.exp3.json");
  assert.equal(avatarExpression("chitose", "surprise"), "Surprised.exp3.json");
});

test("avatar preference persists only approved IDs and falls back to the female guide", () => {
  const values = new Map();
  const storage = {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
  };

  assert.equal(loadAvatarPreference(storage), DEFAULT_AVATAR_ID);
  assert.equal(saveAvatarPreference(storage, "chitose"), "chitose");
  assert.equal(loadAvatarPreference(storage), "chitose");
  assert.equal(saveAvatarPreference(storage, "haruto"), DEFAULT_AVATAR_ID);
  assert.equal(loadAvatarPreference(storage), DEFAULT_AVATAR_ID);
  assert.equal(saveAvatarPreference(storage, "remote-model"), DEFAULT_AVATAR_ID);
  assert.equal(loadAvatarPreference(storage), DEFAULT_AVATAR_ID);
});
