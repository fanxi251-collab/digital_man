import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const haruRoot = path.join(
  frontendRoot,
  "public",
  "digital-human",
  "live2d",
  "haru_greeter",
);

function readJson(relativePath) {
  return JSON.parse(fs.readFileSync(path.join(haruRoot, relativePath), "utf8"));
}

test("Haru pose defaults select the same arms as the idle motion first frame", () => {
  const model = readJson("haru_greeter_t05.model3.json");
  const pose = readJson(model.FileReferences.Pose);
  const idleDefinition = model.FileReferences.Motions[""][0];
  const idle = readJson(idleDefinition.File);
  const initialPartOpacity = new Map(
    idle.Curves
      .filter((curve) => curve.Target === "PartOpacity")
      .map((curve) => [curve.Id, curve.Segments[1]]),
  );

  for (const group of pose.Groups) {
    const initiallyVisible = group
      .map((part) => part.Id)
      .filter((partId) => initialPartOpacity.get(partId) === 1);
    assert.equal(initiallyVisible.length, 1, `expected one visible arm in ${group[0].Id}`);
    assert.equal(
      group[0].Id,
      initiallyVisible[0],
      `pose starts ${group[0].Id}, but idle starts ${initiallyVisible[0]}`,
    );
  }
});

test("Haru idle motion does not cross-fade mutually exclusive arm poses on startup", () => {
  const model = readJson("haru_greeter_t05.model3.json");
  const idleDefinition = model.FileReferences.Motions[""][0];

  assert.equal(idleDefinition.File, "motion/haru_g_idle.motion3.json");
  assert.ok(
    idleDefinition.FadeInTime > 0 && idleDefinition.FadeInTime <= 0.02,
    "the renderer defaults to a 500ms fade, which displays both Haru arm poses at once",
  );
});
