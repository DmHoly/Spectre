"use strict";

/* Unit tests for the zoomable structure viewer's view maths (spectre/plugins/structures/static/
   structure-zoom.js : zoomFit, zoomAt, zoomClamp) and for the campaign variants it is fed
   (campaign-carousel.js::variantZoomItems). Run with:

     node --test

   Both files are loaded as-is in Node's main context, like the page's <script> tags: neither
   touches the DOM until a viewer is actually opened. */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const STATIC = path.join(__dirname, "..", "spectre", "plugins", "structures", "static");

function load(file, names) {
  const filename = path.join(STATIC, file);
  return vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ ${names.join(", ")} })`, { filename });
}

const { zoomFit, zoomAt, zoomClamp, STRUCTURE_ZOOM } = load("structure-zoom.js", ["zoomFit", "zoomAt", "zoomClamp", "STRUCTURE_ZOOM"]);
const { variantZoomItems } = load("campaign-carousel.js", ["variantZoomItems"]);

const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} ≉ ${b}`);

test("zoomFit fits the structure inside the frame, margins included, and centres it", () => {
  const pad = STRUCTURE_ZOOM.pad;
  // limited by the height: 300 px of room for 50 units
  const view = zoomFit(100, 50, 1000 + 2 * pad, 300 + 2 * pad);
  close(view.k, 6);
  close(view.x, (1000 + 2 * pad - 600) / 2);
  close(view.y, pad);
});

test("zoomAt keeps the point under the cursor where it is", () => {
  const view = { k: 2, x: 30, y: -10 };
  const [px, py] = [250, 140];
  const before = [(px - view.x) / view.k, (py - view.y) / view.k];
  const next = zoomAt(view, 5, px, py);
  close(next.k, 5);
  close((px - next.x) / next.k, before[0]);
  close((py - next.y) / next.k, before[1]);
});

test("zoomClamp centres an axis that fits, and keeps a larger one from leaving the frame", () => {
  const pad = STRUCTURE_ZOOM.pad;
  // 100 × 50 units at k = 4 : 400 px wide (fits in 800), 200 px high (not in 120)
  const pushed = zoomClamp({ k: 4, x: -500, y: 90 }, 100, 50, 800, 120);
  close(pushed.x, 200); // centred
  close(pushed.y, pad); // its top edge no further than the margin
  const pulled = zoomClamp({ k: 4, x: 0, y: -500 }, 100, 50, 800, 120);
  close(pulled.y, 120 - 200 - pad); // its bottom edge no further than the margin
  const inside = zoomClamp({ k: 4, x: 0, y: -40 }, 100, 50, 800, 120);
  close(inside.y, -40); // already in bounds: left alone
});

test("variantZoomItems captions each variant and marks the reference one", () => {
  const variation = {
    svgs: ["<svg/>", "<svg/>", "<svg/>"],
    labels: ["10", "20", "30"],
    factor_labels: ["Épaisseur — Dépôt"],
    factor_values: [[10], [20], [30]],
    reference_index: 1,
  };
  const items = variantZoomItems(variation);
  assert.equal(items.length, 3);
  assert.equal(items[0].html, "<svg/>");
  assert.equal(items[2].caption, "Épaisseur — Dépôt : 30");
  assert.deepEqual(
    items.map((item) => item.badge),
    [null, "RÉF", null]
  );
  // no reference plate in the split: no badge at all ; reference_index absent (older campaigns): the first
  assert.deepEqual(
    variantZoomItems({ ...variation, reference_index: null }).map((item) => item.badge),
    [null, null, null]
  );
  assert.equal(variantZoomItems({ svgs: ["<svg/>"], labels: ["a"] })[0].badge, "RÉF");
});
