import assert from "node:assert/strict";
import test from "node:test";

import {
  loadAmapScript,
  parseLngLat,
  resetAmapLoadPromiseForTests,
} from "../src/lib/amapLoader.js";

test("parseLngLat accepts comma-separated coordinates", () => {
  assert.deepEqual(parseLngLat("120.09,31.424"), [120.09, 31.424]);
});

test("parseLngLat rejects incomplete or non-numeric points", () => {
  assert.equal(parseLngLat(""), null);
  assert.equal(parseLngLat("120.09"), null);
  assert.equal(parseLngLat("abc,def"), null);
  assert.equal(parseLngLat(null), null);
});

test("loadAmapScript short-circuits when AMap is already present", async () => {
  resetAmapLoadPromiseForTests();
  const previousWindow = globalThis.window;
  globalThis.window = { AMap: {} };
  try {
    await assert.doesNotReject(() => loadAmapScript("key", "secret"));
  } finally {
    globalThis.window = previousWindow;
    resetAmapLoadPromiseForTests();
  }
});

test("loadAmapScript reuses one in-flight promise for concurrent callers", async () => {
  resetAmapLoadPromiseForTests();
  const previousWindow = globalThis.window;
  const previousDocument = globalThis.document;
  let createdScript = null;
  let appendCount = 0;
  globalThis.window = {};
  globalThis.document = {
    createElement(tag) {
      assert.equal(tag, "script");
      createdScript = {
        src: "",
        async: false,
        onload: null,
        onerror: null,
      };
      return createdScript;
    },
    head: {
      appendChild() {
        appendCount += 1;
      },
    },
  };

  try {
    const first = loadAmapScript("key-a", "secret-a");
    const second = loadAmapScript("key-b", "secret-b");
    assert.equal(first, second);
    assert.equal(globalThis.window._AMapSecurityConfig.securityJsCode, "secret-a");
    assert.equal(appendCount, 1);
    assert.match(createdScript.src, /key=key-a/);
    createdScript.onload();
    await first;
  } finally {
    globalThis.window = previousWindow;
    globalThis.document = previousDocument;
    resetAmapLoadPromiseForTests();
  }
});
