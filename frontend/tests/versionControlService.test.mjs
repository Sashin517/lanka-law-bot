import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

globalThis.crypto ??= webcrypto;

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
  VersionChainError,
  VersionControlService,
  validateVersionChain,
} = loadTypeScriptModule(
  path.resolve(
    testDirectory,
    "../src/lib/drafting/versionControlService.ts",
  ),
);

const source = {
  citation_id: "[LAW-1]",
  title: "Data Protection Act",
  section: "Section 12",
  year: 2022,
  breadcrumb: null,
  excerpt: "Processing must be lawful.",
};

function documentWith(text) {
  return {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [{ type: "text", text }],
      },
    ],
  };
}

class FakeEditor {
  constructor(document) {
    this.document = structuredClone(document);
  }

  getDocument() {
    return structuredClone(this.document);
  }

  setDocument(document) {
    this.document = structuredClone(document);
  }
}

test("snapshots form an immutable, contiguous parent chain", () => {
  const service = new VersionControlService();
  service.hydrate([], null);
  const originalDocument = documentWith("Original");
  const originalSources = [source];

  const first = service.createSnapshot(
    originalDocument,
    originalSources,
    "Original AI-generated draft",
    "ai",
  );
  const second = service.createSnapshot(
    documentWith("Manually revised"),
    originalSources,
    "Manual edit",
    "user",
  );

  assert.ok(first);
  assert.ok(second);
  assert.equal(first.versionNumber, 1);
  assert.equal(first.parentVersionId, null);
  assert.equal(second.versionNumber, 2);
  assert.equal(second.parentVersionId, first.id);
  validateVersionChain(service.getVersionHistory());

  originalDocument.content[0].content[0].text = "Mutated outside service";
  originalSources[0].title = "Mutated source";
  const persisted = service.getVersion(first.id);
  assert.equal(persisted.content.content[0].content[0].text, "Original");
  assert.equal(persisted.sources[0].title, "Data Protection Act");
});

test("an unchanged document does not create a redundant version", () => {
  const service = new VersionControlService();
  service.hydrate([], null);
  service.createSnapshot(documentWith("Same"), [], "Original", "ai");

  const duplicate = service.createSnapshot(
    documentWith("Same"),
    [],
    "Manual edit",
    "user",
  );

  assert.equal(duplicate, null);
  assert.equal(service.getVersionHistory().length, 1);
});

test("restoring history appends a new latest version without rewriting history", () => {
  const service = new VersionControlService();
  service.hydrate([], null);
  const first = service.createSnapshot(
    documentWith("Original"),
    [source],
    "Original AI-generated draft",
    "ai",
  );
  const second = service.createSnapshot(
    documentWith("Second"),
    [],
    "Manual edit",
    "user",
  );
  const beforeRestore = service.getVersionHistory();
  const editor = new FakeEditor(documentWith("Second"));

  const restored = service.restoreVersion(first.id, editor);

  assert.ok(restored);
  assert.equal(restored.newVersion.versionNumber, 3);
  assert.equal(restored.newVersion.parentVersionId, second.id);
  assert.equal(restored.newVersion.editSummary, "Restored from Version 1.");
  assert.equal(editor.getDocument().content[0].content[0].text, "Original");
  assert.deepEqual(service.getVersionHistory().slice(0, 2), beforeRestore);
  assert.deepEqual(restored.newVersion.sources, [source]);
  validateVersionChain(service.getVersionHistory());
});

test("hydrate rejects a broken parent link", () => {
  const invalid = [
    {
      id: "v1",
      versionNumber: 1,
      label: "Version 1",
      content: documentWith("Original"),
      sources: [],
      createdAt: new Date(0).toISOString(),
      createdBy: "ai",
      editSummary: "Original",
      parentVersionId: "missing",
    },
  ];

  assert.throws(() => validateVersionChain(invalid), VersionChainError);
});

test("hydrate rejects malformed persisted snapshot data", () => {
  const invalid = [
    {
      id: "v1",
      versionNumber: 1,
      label: "Version 1",
      content: null,
      sources: [],
      createdAt: "not-a-date",
      createdBy: "ai",
      editSummary: "Original",
      parentVersionId: null,
    },
  ];

  assert.throws(() => validateVersionChain(invalid), VersionChainError);
});
