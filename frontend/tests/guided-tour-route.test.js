import assert from "node:assert/strict";
import test from "node:test";

import { normalizeTourRoute } from "../src/features/guided-tour/lib/tourRoute.js";

test("normalizes a V2 route summary into an executable tour", () => {
  const route = normalizeTourRoute({
    schema_version: 2,
    origin: "灵山大佛",
    destination: "九龙灌浴",
    mode: "walking",
    polyline: ["120.096477,31.430194", "120.099984,31.424601"],
  });

  assert.equal(route.routeId, "ai:灵山大佛:九龙灌浴:walking");
  assert.equal(route.name, "灵山大佛 → 九龙灌浴");
  assert.equal(route.mode, "walking");
  assert.equal(route.points.length, 2);
  assert.ok(route.totalDistance > 600);
});

test("normalizes a legacy amap source without copying source detection", () => {
  const route = normalizeTourRoute({
    metadata: {
      source_type: "amap_route",
      origin: "旧起点",
      destination: "旧终点",
      polyline: ["120.1,31.5", "120.2,31.6"],
      steps: [{ instruction: "向前" }],
    },
  });

  assert.equal(route.name, "旧起点 → 旧终点");
  assert.equal(route.mode, "walking");
  assert.equal(route.points.length, 2);
});

test("rejects routes without at least two distinct valid points", () => {
  assert.equal(normalizeTourRoute(null), null);
  assert.equal(normalizeTourRoute({ polyline: ["120.1,31.5"] }), null);
  assert.equal(normalizeTourRoute({ polyline: ["bad", "120.1,31.5"] }), null);
  assert.equal(normalizeTourRoute({ polyline: ["120.1,31.5", "120.1,31.5"] }), null);
});
