"use strict";

/* Unit tests for the parts of the structure comparator's widget that need no DOM
   (spectre/plugins/comparator/static/comparator-table.js) : the tokens the pages build for a line
   (they must read as the server's comparator.service parses them), the comparator's address, and
   the summary sentence of a comparison. Run with:

     node --test

   The file is loaded as-is in Node's main context, like the page's <script> tag: nothing touches
   the DOM until a table is mounted. */

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const filename = path.join(__dirname, "..", "spectre", "plugins", "comparator", "static", "comparator-table.js");
const { Comparator } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ Comparator })`, { filename });

// comparator/service.py : _STUDY_RE
const STUDY_RE = /^study:([^/@~\s]+)\/([^/@~\s]+)(?:@([^/@~\s]+))?(?:~(\d{1,3}))?$/;

test("a study token names the line, its version and its variant the way the server reads them", () => {
  assert.equal(Comparator.studyItem("epi", "led-bleue"), "study:epi/led-bleue");
  assert.equal(Comparator.studyItem("epi", "led-bleue", "exp_0123456789abcdef"), "study:epi/led-bleue@exp_0123456789abcdef");
  assert.equal(Comparator.studyItem("epi", "split", "exp_0123456789abcdef", 0), "study:epi/split@exp_0123456789abcdef~0");
  assert.equal(Comparator.studyItem("epi", "split", null, 2), "study:epi/split~2");
  const [, slug, line, version, place] = Comparator.studyItem("epi", "split", "exp_0123456789abcdef", 3).match(STUDY_RE);
  assert.deepEqual([slug, line, version, place], ["epi", "split", "exp_0123456789abcdef", "3"]);
});

test("wafer and reference tokens", () => {
  assert.equal(Comparator.waferItem("W12-A3"), "wafer:W12-A3");
  assert.equal(Comparator.referenceItem("led", "1.1"), "reference:led@1.1");
  assert.equal(Comparator.referenceItem("led"), "reference:led");
});

test("the comparator's address carries the lines in order, and the baseline when it is not the first", () => {
  const url = Comparator.pageUrl(["wafer:W 1", "study:epi/led@exp_1"], 1);
  const params = new URLSearchParams(url.split("?")[1]);
  assert.ok(url.startsWith("/comparateur?"));
  assert.deepEqual(params.getAll("item"), ["wafer:W 1", "study:epi/led@exp_1"]);
  assert.equal(params.get("base"), "1");
  assert.equal(new URLSearchParams(Comparator.pageUrl(["wafer:W1"], 0).split("?")[1]).get("base"), null);
});

test("the summary says what differs from the baseline, in the legend's words", () => {
  const none = { changed: 0, added_params: 0, added_layers: 0, moved_layers: 0, absent_layers: 0 };
  assert.equal(Comparator.summaryText(none), "");
  assert.equal(
    Comparator.summaryText({ changed: 3, added_params: 1, added_layers: 1, moved_layers: 2, absent_layers: 1 }),
    "3 paramètres modifiés · 1 paramètre ajouté · 1 couche en plus · 2 étapes déplacées · 1 couche absente"
  );
});
