import assert from "node:assert/strict";
import test from "node:test";

import {
  buildPublishedTourStops,
  stopsNearRoute,
} from "../src/features/guided-tour/lib/tourStops.js";

const core = [{
  stop_id: "grand-buddha",
  attraction_name: "灵山大佛",
  longitude: 120,
  latitude: 31,
  narration_text: "审核讲解",
  local_audio_url: "/digital-human/narration/xiaoxiao/grand-buddha.mp3",
}];

test("published stop builder preserves approved core narration and adds safe summaries", () => {
  const stops = buildPublishedTourStops([
    {
      attraction_id: "core-record",
      name: "灵山大佛",
      summary: "数据库摘要不覆盖审核讲解",
      longitude: 120,
      latitude: 31,
      status: "published",
    },
    {
      attraction_id: "other",
      name: "其他景点",
      summary: "公开摘要",
      longitude: 120.001,
      latitude: 31,
      status: "published",
    },
    { attraction_id: "draft", name: "草稿", summary: "草稿", longitude: 120, latitude: 31, status: "draft" },
    { attraction_id: "empty", name: "空摘要", summary: "", longitude: 120, latitude: 31, status: "published" },
  ], core);

  assert.equal(stops.length, 2);
  assert.equal(stops[0].narration_text, "审核讲解");
  assert.equal(stops[0].attraction_id, "core-record");
  assert.equal(stops[1].narration_text, "公开摘要");
  assert.equal(stops[1].local_audio_url, undefined);
});

test("AI routes keep only stops close to their path", () => {
  const route = { points: [{ longitude: 120, latitude: 31 }, { longitude: 120.01, latitude: 31 }] };
  const candidates = [
    { stop_id: "near", longitude: 120.005, latitude: 31.0001 },
    { stop_id: "far", longitude: 120.005, latitude: 31.01 },
  ];
  assert.deepEqual(stopsNearRoute(candidates, route, 60).map((stop) => stop.stop_id), ["near"]);
});
