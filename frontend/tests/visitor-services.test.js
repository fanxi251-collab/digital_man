import test from "node:test";
import assert from "node:assert/strict";

import { filterFoods } from "../src/features/food/lib/foodFilters.js";
import { filterAttractions } from "../src/features/explore/lib/attractionFilters.js";
import { fetchWithNetworkRetry } from "../src/lib/fetchWithNetworkRetry.js";
import { normalizeAttractionPlace, normalizeFoodPlace } from "../src/lib/mapPlaces.js";
import { getOrCreateVisitorId } from "../src/lib/visitorIdentity.js";
import { fetchVisitorAttractions, fetchVisitorFoods } from "../src/lib/visitorCatalog.js";

test("visitor identity reuses storage and creates one stable anonymous id", () => {
  const values = new Map();
  const storage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
  };
  const cryptoLike = { randomUUID: () => "12345678-1234-1234-1234-123456789abc" };

  const first = getOrCreateVisitorId(storage, cryptoLike);
  const second = getOrCreateVisitorId(storage, { randomUUID: () => "different" });

  assert.equal(first, "visitor_12345678123412341234123456789abc");
  assert.equal(second, first);
});


test("food filters combine scope category taste price and vegetarian preference", () => {
  const foods = [
    {
      name: "灵山蔬食馆",
      summary: "江南素食",
      scope: "inside",
      category: "素食",
      taste_tags: ["清淡", "江南"],
      signature_dishes: ["灵山素面"],
      price_level: 2,
      vegetarian_friendly: true,
    },
    {
      name: "太湖渔村",
      summary: "湖鲜",
      scope: "nearby",
      category: "正餐",
      taste_tags: ["鲜美"],
      signature_dishes: ["太湖白鱼"],
      price_level: 3,
      vegetarian_friendly: false,
    },
  ];

  const visible = filterFoods(foods, {
    keyword: "素面",
    scope: "inside",
    category: "素食",
    taste: "清淡",
    priceLevel: "2",
    vegetarianOnly: true,
  });

  assert.deepEqual(visible.map((item) => item.name), ["灵山蔬食馆"]);
});


test("attraction filters match keyword and category", () => {
  const attractions = [
    {
      name: "灵山大佛",
      summary: "核心景观",
      tags: ["地标"],
      category: "地标",
    },
    {
      name: "九龙灌浴",
      summary: "水幕表演",
      tags: ["演出"],
      category: "体验",
    },
  ];

  assert.deepEqual(
    filterAttractions(attractions, { keyword: "大佛", category: "地标" }).map((item) => item.name),
    ["灵山大佛"],
  );
  assert.deepEqual(
    filterAttractions(attractions, { category: "体验" }).map((item) => item.name),
    ["九龙灌浴"],
  );
});


test("visitor catalog helpers parse list payloads and surface API errors", async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).includes("/attractions")) {
      return {
        ok: true,
        async json() {
          return { attractions: [{ attraction_id: "a1" }] };
        },
      };
    }
    return {
      ok: false,
      status: 503,
      async json() {
        return { detail: "美食服务暂不可用" };
      },
    };
  };
  try {
    assert.deepEqual(await fetchVisitorAttractions(), { attractions: [{ attraction_id: "a1" }] });
    await assert.rejects(() => fetchVisitorFoods(), /美食服务暂不可用/);
  } finally {
    globalThis.fetch = previousFetch;
  }
});


test("map places preserve source identity and use distinct attraction and food kinds", () => {
  const attraction = normalizeAttractionPlace({
    attraction_id: "attr_1",
    name: "灵山大佛",
    summary: "核心景观",
    longitude: 120.09,
    latitude: 31.43,
  });
  const food = normalizeFoodPlace({
    food_id: "food_1",
    name: "灵山蔬食馆",
    summary: "景区餐饮",
    longitude: 120.1,
    latitude: 31.42,
  });

  assert.equal(attraction.place_id, "attraction:attr_1");
  assert.equal(attraction.kind, "attraction");
  assert.equal(food.place_id, "food:food_1");
  assert.equal(food.kind, "food");
});


test("feedback history retries one transient network failure", async () => {
  let attempts = 0;
  const response = { ok: true, json: async () => ({ feedback: [] }) };
  const fetchImpl = async () => {
    attempts += 1;
    if (attempts === 1) throw new TypeError("Failed to fetch");
    return response;
  };

  const result = await fetchWithNetworkRetry("/api/visitor/feedback", {
    fetchImpl,
    retries: 1,
    wait: async () => {},
  });

  assert.equal(result, response);
  assert.equal(attempts, 2);
});
