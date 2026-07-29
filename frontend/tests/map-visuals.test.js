import assert from "node:assert/strict";
import test from "node:test";

import { createPlaceMarkerElement } from "../src/lib/mapVisuals.js";

test("place markers include selected styling hooks", () => {
  const previousDocument = globalThis.document;
  globalThis.document = {
    createElement(tag) {
      const element = {
        tagName: String(tag).toUpperCase(),
        className: "",
        title: "",
        children: [],
        appendChild(child) {
          this.children.push(child);
          return child;
        },
        setAttribute() {},
      };
      return element;
    },
  };
  try {
    const marker = createPlaceMarkerElement(
      { kind: "attraction", name: "灵山大佛" },
      true,
    );
    assert.match(marker.className, /map-place-marker/);
    assert.match(marker.className, /is-attraction/);
    assert.match(marker.className, /is-selected/);
    assert.equal(marker.children[0].className, "map-place-marker-core");
  } finally {
    globalThis.document = previousDocument;
  }
});
