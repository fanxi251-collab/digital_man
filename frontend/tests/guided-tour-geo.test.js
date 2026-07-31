import assert from "node:assert/strict";
import test from "node:test";

import {
  buildRouteMetrics,
  distanceMeters,
  interpolateRoutePosition,
  parseTourPoint,
} from "../src/features/guided-tour/lib/geo.js";

test("guided tour points accept route strings, arrays, and location objects", () => {
  assert.deepEqual(parseTourPoint("120.1,31.5"), { longitude: 120.1, latitude: 31.5 });
  assert.deepEqual(parseTourPoint([120.2, 31.6]), { longitude: 120.2, latitude: 31.6 });
  assert.deepEqual(parseTourPoint({ longitude: "120.3", latitude: "31.7" }), {
    longitude: 120.3,
    latitude: 31.7,
  });
  assert.equal(parseTourPoint("bad-point"), null);
  assert.equal(parseTourPoint([181, 31]), null);
  assert.equal(parseTourPoint({ longitude: 120, latitude: 91 }), null);
});

test("haversine distance is stable for equal and nearby points", () => {
  const point = { longitude: 120.1, latitude: 31.5 };
  assert.equal(distanceMeters(point, point), 0);

  const aboutOneHundredMetersNorth = { longitude: 120.1, latitude: 31.5009 };
  assert.ok(Math.abs(distanceMeters(point, aboutOneHundredMetersNorth) - 100.1) < 1);
  assert.equal(distanceMeters(point, null), Number.POSITIVE_INFINITY);
});

test("route metrics remove adjacent duplicates and interpolate by travelled distance", () => {
  const metrics = buildRouteMetrics([
    "120.1000,31.5000",
    "120.1000,31.5000",
    "120.1000,31.5009",
    "120.1010,31.5009",
  ]);

  assert.equal(metrics.points.length, 3);
  assert.equal(metrics.segments.length, 2);
  assert.ok(metrics.totalDistance > 190);

  assert.deepEqual(interpolateRoutePosition(metrics, -1), {
    longitude: 120.1,
    latitude: 31.5,
    heading: 0,
  });
  assert.deepEqual(interpolateRoutePosition(metrics, metrics.totalDistance + 1), {
    longitude: 120.101,
    latitude: 31.5009,
    heading: 90,
  });

  const midpoint = interpolateRoutePosition(metrics, metrics.segments[0].length / 2);
  assert.ok(Math.abs(midpoint.latitude - 31.50045) < 0.000001);
  assert.ok(Math.abs(midpoint.longitude - 120.1) < 0.000001);
  assert.equal(midpoint.heading, 0);
});

test("empty route metrics cannot produce a position", () => {
  assert.equal(buildRouteMetrics(["bad"]).totalDistance, 0);
  assert.equal(interpolateRoutePosition(buildRouteMetrics([]), 10), null);
});
