import assert from "node:assert/strict";
import test from "node:test";

import {
  buildProjectionBounds,
  projectTourPoint,
  projectTourPolyline,
} from "../src/features/guided-tour/lib/fallbackProjection.js";

test("fallback projection keeps route points inside a padded SVG viewport", () => {
  const points = [
    { longitude: 120, latitude: 31 },
    { longitude: 120.01, latitude: 31.02 },
  ];
  const bounds = buildProjectionBounds(points, 0.1);
  const first = projectTourPoint(points[0], bounds);
  const last = projectTourPoint(points[1], bounds);

  assert.ok(first.x >= 0 && first.x <= 100);
  assert.ok(first.y >= 0 && first.y <= 100);
  assert.ok(last.x >= 0 && last.x <= 100);
  assert.ok(last.y >= 0 && last.y <= 100);
  assert.ok(first.x < last.x);
  assert.ok(first.y > last.y);
  assert.equal(projectTourPolyline(points, bounds).split(" ").length, 2);
});

test("fallback projection handles a zero-span route without NaN", () => {
  const point = { longitude: 120, latitude: 31 };
  const bounds = buildProjectionBounds([point]);
  assert.deepEqual(projectTourPoint(point, bounds), { x: 50, y: 50 });
  assert.equal(projectTourPoint(null, bounds), null);
});
