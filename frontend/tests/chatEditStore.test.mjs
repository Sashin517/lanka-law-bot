import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);
const storeFilename = path.resolve(
  testDirectory,
  "../src/store/chatEditStore.ts",
);

function loadTypeScriptModule(filename) {
  const source = fs.readFileSync(filename, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
  const loaded = new Module(filename);
  loaded.filename = filename;
  loaded.paths = Module._nodeModulePaths(path.dirname(filename));
  loaded.require = nodeRequire;
  loaded._compile(output, `${filename}.js`);
  return loaded.exports;
}

const { useChatEditStore } = loadTypeScriptModule(storeFilename);

test("capturing editor text does not request chat composer focus", () => {
  useChatEditStore.getState().reset();
  const selection = {
    text: "selected clause",
    from: 4,
    to: 19,
    nodeContext: "paragraph",
  };

  useChatEditStore.getState().setSelection(selection);

  const state = useChatEditStore.getState();
  assert.deepEqual(state.currentSelection, selection);
  assert.equal(state.composerFocusRequested, false);
});

test("an explicit Ask/Edit action creates a consumable focus request", () => {
  useChatEditStore.getState().reset();
  const selection = {
    text: "selected clause",
    from: 4,
    to: 19,
    nodeContext: "paragraph",
  };
  useChatEditStore.getState().setSelection(selection);

  useChatEditStore.getState().requestComposerFocus();
  assert.equal(useChatEditStore.getState().composerFocusRequested, true);

  useChatEditStore.getState().consumeComposerFocusRequest();
  const state = useChatEditStore.getState();
  assert.equal(state.composerFocusRequested, false);
  assert.deepEqual(state.currentSelection, selection);
});
