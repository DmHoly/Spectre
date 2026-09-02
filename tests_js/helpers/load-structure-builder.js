"use strict";

/* Loads real production files from spectre/api/static/js/structure-builder/ and runs them in
   Node's main context (vm.runInThisContext, not a separate vm.createContext sandbox) - the same
   "plain <script> tags share one global scope" model the browser uses (see
   structure-builder.html), so functions/consts defined in one file are visible to files loaded
   after it, exactly like in the page. No bundler, no transpilation: this runs the exact source
   the browser gets, unmodified.

   Running in the *main* context (rather than an isolated sandbox) is deliberate, not just
   simpler: each file is compiled with its own real absolute path as the vm script's filename, so
   `node --test --experimental-test-coverage` attributes the lines it executes back to that file
   and reports it in the coverage table like any other module - a separate vm realm is invisible
   to that instrumentation.

   Only a minimal `document`/`window` stub is installed on the real global object (just enough
   that the top-level `document.getElementById(...).addEventListener(...)` wiring every module
   does on load doesn't throw) - deliberately not a real DOM. That keeps these tests scoped to the
   pure, DOM-independent logic (Python code generation, step summaries, unit conversion...);
   anything that reads real form values needs a browser and is covered by Playwright instead (see
   the QA scripts used during development), not this harness. */

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "..", "spectre", "api", "static", "js", "structure-builder");

function fakeElement() {
  const el = {
    style: {},
    dataset: {},
    innerHTML: "",
    addEventListener() {},
    dispatchEvent() {
      return true;
    },
    appendChild() {},
    remove() {},
    scrollIntoView() {},
    querySelector() {
      return null;
    },
    querySelectorAll() {
      return [];
    },
  };
  return el;
}

function makeDocument() {
  return {
    getElementById() {
      return fakeElement();
    },
    createElement() {
      return fakeElement();
    },
    querySelectorAll() {
      return [];
    },
  };
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/**
 * @param {string[]} filenames - structure-builder/ files to load, in dependency order (the same
 *   order structure-builder.html gives them as <script> tags).
 * @param {string[]} exportNames - every top-level name (function or `const`) the caller wants
 *   back. A `function` declaration already attaches itself to `global` for free (how non-strict
 *   top-level function declarations behave); a `const`/`let` binding never does on its own - it
 *   stays visible only to code run afterwards *in the same context*, not to the Node code that
 *   called runInThisContext. Rather than telling those two cases apart, one extra script just
 *   copies every requested name onto `global` from inside that shared scope, which works either
 *   way (re-assigning an already-global function to itself is a no-op).
 * @returns an object with exactly those names, e.g. `{ pyStepCode, STEP_KIND_DEFS }`.
 */
function loadStructureBuilder(filenames, exportNames) {
  global.document = makeDocument();
  global.window = { location: { pathname: "/projets/test-js/structures/nouvelle", search: "" } };
  global.escapeHtml = escapeHtml;

  for (const filename of filenames) {
    const filePath = path.join(JS_DIR, filename);
    const code = fs.readFileSync(filePath, "utf8");
    vm.runInThisContext(code, { filename: filePath });
  }

  const copyOnto = exportNames.map((name) => `global[${JSON.stringify(name)}] = ${name};`).join("\n");
  vm.runInThisContext(copyOnto, { filename: "(export bindings)" });

  const exported = {};
  for (const name of exportNames) exported[name] = global[name];
  return exported;
}

module.exports = { loadStructureBuilder };
