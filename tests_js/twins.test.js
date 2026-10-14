"use strict";

/* Unit tests for the sentence the twins panel writes for each variation
   (spectre/plugins/twins/static/twins.js). The server lists variations as
   {kind, step, parameter, from, to} (comparator/table.py: differences). Run with:

     node --test
*/

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const filename = path.join(__dirname, "..", "spectre", "plugins", "twins", "static", "twins.js");
const { Twins } = vm.runInThisContext(`${fs.readFileSync(filename, "utf8")}\n;({ Twins })`, { filename });

test("a changed parameter says what it was and what it became", () => {
  const text = Twins.differenceText({ kind: "changed", step: "Oxyde", parameter: "Épaisseur", from: "20 nm", to: "35 nm" });
  assert.equal(text, "Oxyde · Épaisseur : 20 nm → 35 nm");
});

test("an added parameter, a layer in addition, a moved step and a missing layer", () => {
  assert.equal(Twins.differenceText({ kind: "added_param", step: "GaN", parameter: "Dopage", from: null, to: "3e18 cm⁻³" }), "GaN · Dopage ajouté : 3e18 cm⁻³");
  assert.equal(Twins.differenceText({ kind: "added_layer", step: "Contact", parameter: null, from: null, to: null }), "Couche en plus : Contact");
  assert.equal(Twins.differenceText({ kind: "moved", step: "Puits", parameter: null, from: null, to: null }), "Étape déplacée : Puits");
  assert.equal(Twins.differenceText({ kind: "absent", step: "Ouverture", parameter: null, from: null, to: null }), "Couche absente : Ouverture");
});
