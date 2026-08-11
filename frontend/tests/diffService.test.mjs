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

const {
  DiffService,
  StructuralDiffStrategy,
  TextDiffStrategy,
} = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/diffService.ts"),
);

function paragraph(text, marks) {
  return {
    type: "paragraph",
    content: text
      ? [{ type: "text", text, ...(marks ? { marks } : {}) }]
      : [],
  };
}

function documentWith(...paragraphs) {
  return { type: "doc", content: paragraphs.map((text) => paragraph(text)) };
}

test("text diff returns no changes for identical canonical documents", () => {
  const strategy = new TextDiffStrategy();
  const document = documentWith("No changes");
  assert.deepEqual(strategy.computeDiff(document, structuredClone(document)), []);
});

test("text diff coalesces adjacent deletion and insertion into a modification", () => {
  const strategy = new TextDiffStrategy();
  const changes = strategy.computeDiff(
    documentWith("The old clause applies."),
    documentWith("The revised clause applies."),
  );

  assert.equal(changes.length, 1);
  assert.equal(changes[0].type, "replace");
  // The semantic cleanup preserves the shared trailing "d" as unchanged.
  assert.equal(changes[0].oldContent, "ol");
  assert.equal(changes[0].newContent, "revise");
  assert.deepEqual(changes[0].position, { from: 5, to: 11 });
  assert.equal(changes[0].path, "content.0.content.0");
});

test("insertions and deletions are anchored to current ProseMirror positions", () => {
  const strategy = new TextDiffStrategy();
  const insertion = strategy.computeDiff(
    documentWith("Clause"),
    documentWith("Clause added"),
  );
  const deletion = strategy.computeDiff(
    documentWith("Clause removed"),
    documentWith("Clause"),
  );

  assert.equal(insertion[0].type, "insert");
  assert.deepEqual(insertion[0].position, { from: 7, to: 13 });
  assert.equal(deletion[0].type, "delete");
  assert.deepEqual(deletion[0].position, { from: 7, to: 7 });
  assert.equal(deletion[0].oldContent, " removed");
});

test("multi-block text maps changes into the correct later text block", () => {
  const strategy = new TextDiffStrategy();
  const changes = strategy.computeDiff(
    documentWith("First", "Second"),
    documentWith("First", "Revised second"),
  );

  assert.equal(changes.length, 1);
  assert.equal(changes[0].path, "content.1.content.0");
  assert.ok(changes[0].position.from >= 8);
  assert.ok(changes[0].position.to > changes[0].position.from);
});

test("structural strategy reports formatting-only RFC 6902 changes", () => {
  const original = { type: "doc", content: [paragraph("Important")] };
  const current = {
    type: "doc",
    content: [paragraph("Important", [{ type: "bold" }])],
  };
  const changes = new StructuralDiffStrategy().computeDiff(original, current);

  assert.ok(changes.length > 0);
  assert.ok(changes.every((change) => change.type === "format_change"));
  assert.ok(changes.some((change) => change.path.includes("marks")));
});

test("DiffService can swap strategies without changing its public contract", () => {
  const service = new DiffService({
    computeDiff: () => [
      {
        type: "format_change",
        path: "/custom",
        position: { from: 1, to: 1 },
      },
    ],
  });
  assert.equal(service.computeDiff(documentWith("A"), documentWith("B")).length, 1);

  service.setStrategy(new TextDiffStrategy());
  assert.equal(
    service.computeDiff(documentWith("A"), documentWith("B"))[0].type,
    "replace",
  );
});
