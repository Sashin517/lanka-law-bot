import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);
const storeFilename = path.resolve(testDirectory, "../src/store/themeStore.ts");

function createStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

function loadStore(storage) {
  globalThis.localStorage = storage;
  const source = fs.readFileSync(storeFilename, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  }).outputText;
  const loaded = new Module(storeFilename);
  loaded.filename = storeFilename;
  loaded.paths = Module._nodeModulePaths(path.dirname(storeFilename));
  loaded.require = (id) => nodeRequire(id);
  loaded._compile(output, `${storeFilename}.js`);
  return loaded.exports;
}

test("theme store defaults to dark and toggles both directions", () => {
  const { useThemeStore } = loadStore(createStorage());

  assert.equal(useThemeStore.getState().theme, "dark");
  useThemeStore.getState().toggleTheme();
  assert.equal(useThemeStore.getState().theme, "light");
  useThemeStore.getState().toggleTheme();
  assert.equal(useThemeStore.getState().theme, "dark");
});

test("theme preference is persisted using the shared storage contract", () => {
  const storage = createStorage();
  const { THEME_STORAGE_KEY, useThemeStore } = loadStore(storage);

  useThemeStore.getState().setTheme("light");

  const persisted = JSON.parse(storage.getItem(THEME_STORAGE_KEY));
  assert.equal(persisted.state.theme, "light");
  assert.equal(persisted.version, 1);
});
