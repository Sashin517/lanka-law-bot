import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);

function loadTypeScriptModule(filename, dependencies = {}) {
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
  loaded.require = (id) => dependencies[id] ?? nodeRequire(id);
  loaded._compile(output, `${filename}.js`);
  return loaded.exports;
}

const formatting = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/formatting.ts"),
);
const editorServiceModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/editorService.ts"),
  { "@/lib/drafting/formatting": formatting },
);
const { EditorService } = editorServiceModule;

class FakeEditor {
  constructor() {
    this.calls = [];
    this.listeners = new Map();
    this.blockAttrs = {
      textAlign: "justify",
      indentLevel: 2,
      lineSpacing: 1.15,
      spacingBefore: 6,
      spacingAfter: 12,
    };
    this.textStyleAttrs = { fontSize: 14 };
    this.active = new Set(["heading-3", "bold", "underline"]);
    this.history = { undo: true, redo: false };
  }

  isActive(name, attrs) {
    return name === "heading"
      ? this.active.has(`heading-${attrs.level}`)
      : this.active.has(name);
  }

  getAttributes(name) {
    return name === "textStyle" ? this.textStyleAttrs : this.blockAttrs;
  }

  can() {
    return {
      undo: () => this.history.undo,
      redo: () => this.history.redo,
    };
  }

  on(event, listener) {
    this.listeners.set(event, listener);
  }

  off(event, listener) {
    if (this.listeners.get(event) === listener) this.listeners.delete(event);
  }

  chain() {
    const calls = this.calls;
    const chain = new Proxy(
      {},
      {
        get(_target, property) {
          if (property === "run") return () => true;
          return (...args) => {
            calls.push([property, ...args]);
            return chain;
          };
        },
      },
    );
    return chain;
  }
}

test("formatting allowlists accept only controlled legal-document values", () => {
  assert.equal(formatting.isAllowedFontSize(14), true);
  assert.equal(formatting.isAllowedFontSize(13), false);
  assert.equal(formatting.normalizeIndentLevel(-4), 0);
  assert.equal(formatting.normalizeIndentLevel(99), formatting.MAX_INDENT_LEVEL);
  assert.equal(formatting.normalizeLineSpacing(9), formatting.DEFAULT_LINE_SPACING);
  assert.equal(
    formatting.normalizeParagraphSpacing(7),
    formatting.DEFAULT_PARAGRAPH_SPACING,
  );
  assert.equal(formatting.parsePointValue("12pt"), 12);
  assert.ok(Number.isNaN(formatting.parsePointValue("12px")));
});

test("EditorService exposes formatting state without leaking editor internals", () => {
  const service = new EditorService(new FakeEditor());
  assert.deepEqual(service.getFormattingState(), {
    blockType: "heading-3",
    fontSize: 14,
    alignment: "justify",
    indentLevel: 2,
    lineSpacing: 1.15,
    spacingBefore: 6,
    spacingAfter: 12,
    bold: true,
    italic: false,
    underline: true,
    strike: false,
    canUndo: true,
    canRedo: false,
  });
});

test("EditorService routes formatting through focused Tiptap chains", () => {
  const editor = new FakeEditor();
  const service = new EditorService(editor);

  assert.equal(service.setBlockType("heading-4"), true);
  assert.equal(service.toggleInlineFormat("strike"), true);
  assert.equal(service.setFontSize(18), true);
  assert.equal(service.setTextAlignment("center"), true);
  assert.equal(service.setIndentLevel(4), true);
  assert.equal(service.setLineSpacing(2), true);
  assert.equal(service.setParagraphSpacingBefore(18), true);
  assert.equal(service.setParagraphSpacingAfter(24), true);
  assert.equal(service.undo(), true);
  assert.equal(service.redo(), true);

  assert.deepEqual(editor.calls.slice(0, 2), [
    ["focus"],
    ["setHeading", { level: 4 }],
  ]);
  assert.ok(
    editor.calls.some(
      ([command, name, attrs]) =>
        command === "setMark" && name === "textStyle" && attrs.fontSize === 18,
    ),
  );
  assert.ok(
    editor.calls.some(
      ([command, name, attrs]) =>
        command === "updateAttributes" &&
        name === "paragraph" &&
        attrs.lineSpacing === 2,
    ),
  );
  assert.ok(editor.calls.some(([command]) => command === "undo"));
  assert.ok(editor.calls.some(([command]) => command === "redo"));
});

test("EditorService subscriptions are initialized and disposed", () => {
  const editor = new FakeEditor();
  const service = new EditorService(editor);
  const states = [];
  const unsubscribe = service.subscribeToFormatting((state) => states.push(state));

  assert.equal(states.length, 1);
  assert.equal(editor.listeners.size, 1);
  editor.listeners.get("transaction")();
  assert.equal(states.length, 2);
  unsubscribe();
  assert.equal(editor.listeners.size, 0);
});
