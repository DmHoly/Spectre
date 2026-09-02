"use strict";

/* Loads real production files from spectre/api/static/js/structure-builder/ into one shared
   Node vm context, the same "plain <script> tags share one global scope" model the browser uses
   (see structure-builder.html) - so functions/consts defined in one file are visible to files
   loaded after it, exactly like in the page. No bundler, no transpilation: this runs the exact
   source the browser gets.

   Only a minimal `document` stub is provided (just enough that the top-level
   `document.getElementById(...).addEventListener(...)` wiring every module does on load doesn't
   throw) - deliberately not a real DOM. That keeps these tests scoped to the pure, DOM-independent
   logic (Python code generation, step summaries, unit conversion...); anything that reads real
   form values needs a browser and is covered by Playwright instead (see the QA scripts used
   during development), not this harness. */

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
 * @param {string[]} [exportNames] - top-level `const`/`let` names to expose on the returned
 *   object. Plain `function` declarations already end up there for free (Node's vm attaches
 *   `var`/function declarations to the context object, but not `const`/`let` bindings - those
 *   stay visible only to code run afterwards *inside* the same context, not to the Node code that
 *   called runInContext) - this list is only for the `const`s a test needs to reach directly.
 * @returns the vm context (sandbox) they were evaluated into - read globals like
 *   `sandbox.pyStepCode` (a function declaration) or `sandbox.STEP_KIND_DEFS` (needs `exportNames`)
 *   off the returned object.
 */
function loadStructureBuilder(filenames, exportNames = []) {
  const sandbox = {
    document: makeDocument(),
    window: { location: { pathname: "/projets/test-js/structures/nouvelle", search: "" } },
    URLSearchParams,
    console,
    escapeHtml,
  };
  vm.createContext(sandbox);
  for (const filename of filenames) {
    const code = fs.readFileSync(path.join(JS_DIR, filename), "utf8");
    vm.runInContext(code, sandbox, { filename });
  }
  if (exportNames.length) {
    const copyOnto = exportNames.map((name) => `this[${JSON.stringify(name)}] = ${name};`).join("\n");
    vm.runInContext(copyOnto, sandbox, { filename: "(export const bindings)" });
  }
  return sandbox;
}

/**
 * Node's `assert.deepEqual`/`deepStrictEqual` treats an array or object built inside the vm
 * sandbox (a different realm, with its own `Array`/`Object` constructors) as never
 * reference-equal to an equivalent literal in the caller's realm, even when every value inside
 * is identical - a JSON round-trip normalizes a vm-realm value into a plain object/array of the
 * caller's own realm so it compares the way it looks.
 */
function toPlain(value) {
  return JSON.parse(JSON.stringify(value));
}

module.exports = { loadStructureBuilder, toPlain };
