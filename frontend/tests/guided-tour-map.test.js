import assert from "node:assert/strict";
import test from "node:test";

import { createGuidedTourMap } from "../src/features/guided-tour/composables/useGuidedTourMap.js";

function amapDouble() {
  const maps = [];
  const polylines = [];
  const markers = [];
  class Map {
    constructor(element, options) {
      this.element = element;
      this.options = options;
      this.removed = [];
      this.centers = [];
      this.destroyed = false;
      maps.push(this);
    }
    remove(items) { this.removed.push(...items); }
    setFitView(items) { this.fitItems = items; }
    setZoomAndCenter(zoom, center) { this.focus = [zoom, center]; }
    setCenter(center) { this.centers.push(center); }
    resize() { this.resized = true; }
    destroy() { this.destroyed = true; }
  }
  class Polyline {
    constructor(options) { Object.assign(this, options); polylines.push(this); }
  }
  class Marker {
    constructor(options) { Object.assign(this, options); this.positions = []; markers.push(this); }
    setPosition(position) { this.position = position; this.positions.push(position); }
  }
  class Pixel { constructor(x, y) { this.x = x; this.y = y; } }
  return { api: { Map, Polyline, Marker, Pixel }, maps, polylines, markers };
}

const route = {
  points: [
    { longitude: 120, latitude: 31 },
    { longitude: 120.01, latitude: 31.01 },
  ],
};
const stops = [{ stop_id: "one", attraction_name: "景点", longitude: 120, latitude: 31 }];

test("guided map always creates an independent 2D AMap instance", async () => {
  const fake = amapDouble();
  const options = {
    configFetcher: async () => ({
      enabled: true,
      js_api_key: "key",
      security_js_code: "code",
      map_style: "amap://styles/normal",
    }),
    scriptLoader: async () => {},
    amap: () => fake.api,
  };
  const first = createGuidedTourMap({ value: {} }, options);
  const second = createGuidedTourMap({ value: {} }, options);
  assert.equal(await first.initialize(route, stops), true);
  assert.equal(await second.initialize(route, stops), true);

  assert.equal(fake.maps.length, 2);
  assert.notEqual(fake.maps[0], fake.maps[1]);
  assert.equal(fake.maps[0].options.viewMode, "2D");
  assert.equal("pitch" in fake.maps[0].options, false);
  first.destroy();
  assert.equal(fake.maps[0].destroyed, true);
  assert.equal(fake.maps[1].destroyed, false);
  second.destroy();
});

test("guided map draws current and preview routes and updates visitor position", async () => {
  const fake = amapDouble();
  const map = createGuidedTourMap({ value: {} }, {
    configFetcher: async () => ({ enabled: true, js_api_key: "key", security_js_code: "code" }),
    scriptLoader: async () => {},
    amap: () => fake.api,
  });
  await map.initialize(route, stops);
  map.renderRoute(route);
  map.previewRoute({ points: [route.points[1], route.points[0]] });
  map.updatePosition({ longitude: 120.005, latitude: 31.005, heading: 45 });
  map.focusStop({ ...stops[0], focus_zoom: 18 });

  assert.ok(fake.polylines.some((line) => line.strokeColor === "#2f7d78"));
  assert.ok(fake.polylines.some((line) => line.strokeColor === "#d4a64c"));
  assert.deepEqual(fake.markers.at(-1).position, [120.005, 31.005]);
  assert.deepEqual(fake.maps[0].focus, [18, [120, 31]]);
  map.destroy();
});

test("missing map configuration activates the local fallback without creating AMap", async () => {
  const fake = amapDouble();
  const map = createGuidedTourMap({ value: {} }, {
    configFetcher: async () => ({ enabled: false, message: "未配置" }),
    scriptLoader: async () => {},
    amap: () => fake.api,
  });
  assert.equal(await map.initialize(route, stops), false);
  assert.equal(map.mode.value, "fallback");
  assert.equal(map.notice.value, "未配置");
  assert.equal(fake.maps.length, 0);
});
