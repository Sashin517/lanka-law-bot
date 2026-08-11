import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { webcrypto } from "node:crypto";
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

const sourcesModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/sources.ts"),
);
const builderModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/documentBuilder.ts"),
  { "@/lib/sources": sourcesModule },
);
const draftingTypes = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/types/drafting.ts"),
);
const apiModule = {
  editDraft: async () => {
    throw new Error("Unexpected default edit API call");
  },
  sendLegalQuery: async () => {
    throw new Error("Unexpected default ask API call");
  },
};
const serviceModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/chatEditService.ts"),
  {
    "@/lib/api": apiModule,
    "@/lib/drafting/documentBuilder": builderModule,
    "@/types/drafting": draftingTypes,
  },
);

const { DocumentBuilder } = builderModule;
const { ChatEditService, StaleDraftEditError, mergeSources } = serviceModule;

const legalSource = {
  citation_id: "[LAW-1]",
  title: "Data Protection Act",
  section: "Section 12",
  year: 2022,
  breadcrumb: null,
  excerpt: "Processing must be lawful.",
};

class FakeEditor {
  constructor(document) {
    this.document = structuredClone(document);
    this.replacements = [];
  }

  getDocument() {
    return structuredClone(this.document);
  }

  setDocument(document) {
    this.document = structuredClone(document);
  }

  replaceSelection(selection, content) {
    this.replacements.push({ selection, content });
    this.document.content[0].content = structuredClone(content);
  }
}

function fakeApi(editResult) {
  const calls = { edit: [], ask: [] };
  return {
    calls,
    implementation: {
      async edit(payload) {
        calls.edit.push(payload);
        return editResult;
      },
      async ask(payload) {
        calls.ask.push(payload);
        return {
          markdown_content: "The clause is consistent with the Act [LAW-1].",
          sources: [legalSource],
        };
      },
    },
  };
}

test("light path captures a pending suggestion and applies one selected range", async () => {
  const builder = new DocumentBuilder();
  const baseDocument = builder.fromMarkdown("Original clause", []);
  const result = {
    edit_type: "replace",
    original_text: "Original clause",
    edited_text: "Revised clause [LAW-1]",
    markdown_content: "Revised clause [LAW-1]",
    sources: [legalSource],
    edit_summary: "Formalized the clause.",
    confidence: "high",
    edit_path: "light",
    execution_trace: null,
  };
  const api = fakeApi(result);
  const service = new ChatEditService(api.implementation, builder);
  const editor = new FakeEditor(baseDocument);

  const suggestion = await service.requestEdit({
    draftId: "draft-1",
    instruction: "Make this formal",
    selection: {
      text: "Original clause",
      from: 1,
      to: 16,
      nodeContext: "paragraph",
    },
    currentDocument: baseDocument,
    currentMarkdown: "Original clause",
    documentIds: ["doc-1"],
  });

  assert.equal(api.calls.edit[0].selected_text, "Original clause");
  assert.equal(editor.getDocument().content[0].content[0].text, "Original clause");

  const applied = service.applySuggestion(suggestion, editor, [], 2);
  assert.equal(editor.replacements.length, 1);
  assert.equal(applied.markdown, "Revised clause [LAW-1]");
  assert.equal(applied.sources[0].citation_id, "[LAW-1]");
  const marks = applied.document.content[0].content.flatMap(
    (node) => node.marks ?? [],
  );
  assert.ok(marks.some((mark) => mark.type === "citationMark"));
  assert.ok(marks.some((mark) => mark.type === "editHighlight"));
});

test("heavy path replaces the full document and preserves execution metadata", async () => {
  const builder = new DocumentBuilder();
  const baseDocument = builder.fromMarkdown("# Old Agreement\n\nOld terms", []);
  const result = {
    edit_type: "full_rewrite",
    original_text: "# Old Agreement\n\nOld terms",
    edited_text: "# Revised Agreement\n\nNew terms [LAW-1]",
    markdown_content: "# Revised Agreement\n\nNew terms [LAW-1]",
    sources: [legalSource],
    edit_summary: "Revised the agreement.",
    confidence: "high",
    edit_path: "heavy",
    execution_trace: {
      plan_type: "planned",
      steps_executed: [{ agent: "drafting", purpose: "Rewrite" }],
      total_steps: 1,
      planning_reasoning: "Complex revision",
      completed_agents: ["drafting"],
    },
  };
  const api = fakeApi(result);
  const service = new ChatEditService(api.implementation, builder);
  const editor = new FakeEditor(baseDocument);
  const suggestion = await service.requestEdit({
    draftId: "draft-2",
    instruction: "Rewrite the entire document",
    selection: null,
    currentDocument: baseDocument,
    currentMarkdown: "# Old Agreement\n\nOld terms",
    documentIds: [],
  });

  const applied = service.applySuggestion(suggestion, editor, [], 2);
  assert.match(applied.markdown, /Revised Agreement/);
  assert.match(applied.markdown, /New terms \[LAW-1\]/);
  assert.equal(applied.editPath, "heavy");
  assert.ok(
    applied.document.content
      .flatMap((node) => node.content ?? [])
      .flatMap((node) => node.marks ?? [])
      .some((mark) => mark.type === "editHighlight"),
  );
});

test("Ask uses the research API and never mutates the editor", async () => {
  const builder = new DocumentBuilder();
  const document = builder.fromMarkdown("A privacy clause", []);
  const editor = new FakeEditor(document);
  const api = fakeApi(null);
  const service = new ChatEditService(api.implementation, builder);

  const answer = await service.ask({
    instruction: "Is this enforceable?",
    selection: {
      text: "privacy clause",
      from: 3,
      to: 17,
      nodeContext: "paragraph",
    },
    currentContent: "A privacy clause",
    documentIds: [],
  });

  assert.match(api.calls.ask[0].question, /without editing the document/);
  assert.match(answer.content, /consistent with the Act/);
  assert.equal(editor.getDocument().content[0].content[0].text, "A privacy clause");
});

test("a response is rejected when the base document changed", async () => {
  const builder = new DocumentBuilder();
  const baseDocument = builder.fromMarkdown("Original", []);
  const result = {
    edit_type: "replace",
    original_text: "Original",
    edited_text: "Suggested",
    markdown_content: "Suggested",
    sources: [],
    edit_summary: "Changed text.",
    confidence: "medium",
    edit_path: "light",
  };
  const api = fakeApi(result);
  const service = new ChatEditService(api.implementation, builder);
  const suggestion = await service.requestEdit({
    draftId: "draft-3",
    instruction: "Change it",
    selection: { text: "Original", from: 1, to: 9, nodeContext: "paragraph" },
    currentDocument: baseDocument,
    currentMarkdown: "Original",
    documentIds: [],
  });
  const editor = new FakeEditor(builder.fromMarkdown("User changed it", []));

  assert.throws(
    () => service.applySuggestion(suggestion, editor, [], 2),
    StaleDraftEditError,
  );
});

test("source merging is deterministic and incoming metadata wins", () => {
  const old = { ...legalSource, title: "Old title" };
  const merged = mergeSources([old], [legalSource]);
  assert.equal(merged.length, 1);
  assert.equal(merged[0].title, "Data Protection Act");
});
