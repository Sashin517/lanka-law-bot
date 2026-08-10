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

const { CitationService } = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/citationService.ts"),
);
const sourcesModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/sources.ts"),
);
const { DocumentBuilder } = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/documentBuilder.ts"),
  { "@/lib/sources": sourcesModule },
);

const legalSource = {
  citation_id: "[LAW-1]",
  title: "Evidence Ordinance",
  section: "Section 5",
  year: 1895,
  breadcrumb: null,
  excerpt: "Relevant evidence may be given.",
  page_start: 12,
  page_end: 13,
  authoritative: true,
};

function citationText(citationId, attrs = {}) {
  return {
    type: "text",
    text: citationId,
    marks: [
      {
        type: "citationMark",
        attrs: { citationId, ...attrs },
      },
    ],
  };
}

test("returns no citations for an empty document", () => {
  const service = new CitationService();
  assert.deepEqual(service.resolveCitations(null, [legalSource]), []);
  assert.deepEqual(
    service.resolveCitations({ type: "doc", content: [] }, [legalSource]),
    [],
  );
});

test("resolves nested citations in document order and counts duplicates", () => {
  const document = {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [
          { type: "text", text: "Authority " },
          citationText("[LAW-1]", {
            sourceType: "legal_authority",
            pageStart: "12",
            authoritative: "true",
          }),
        ],
      },
      {
        type: "bulletList",
        content: [
          {
            type: "listItem",
            content: [
              {
                type: "paragraph",
                content: [
                  citationText("[DOC-2]"),
                  citationText("[LAW-1]"),
                ],
              },
            ],
          },
        ],
      },
    ],
  };

  const citations = new CitationService().resolveCitations(document, [
    legalSource,
  ]);

  assert.equal(citations.length, 2);
  assert.equal(citations[0].citationId, "[LAW-1]");
  assert.equal(citations[0].status, "linked");
  assert.equal(citations[0].occurrenceCount, 2);
  assert.deepEqual(citations[0].firstDocumentPath, [0, 1]);
  assert.equal(citations[0].attrs.pageStart, 12);
  assert.equal(citations[0].attrs.authoritative, true);

  assert.equal(citations[1].citationId, "[DOC-2]");
  assert.equal(citations[1].attrs.sourceType, "user_document");
  assert.equal(citations[1].status, "unresolved");
  assert.equal(citations[1].source, null);
});

test("falls back to marked text and ignores malformed citation marks", () => {
  const document = {
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [
          {
            type: "text",
            text: "[LAW-1]",
            marks: [{ type: "citationMark" }],
          },
          {
            type: "text",
            text: "not-a-citation",
            marks: [{ type: "citationMark", attrs: {} }],
          },
        ],
      },
    ],
  };

  const citations = new CitationService().resolveCitations(document, [
    legalSource,
  ]);
  assert.equal(citations.length, 1);
  assert.equal(citations[0].citationId, "[LAW-1]");
  assert.equal(citations[0].status, "linked");
});

test("resolves citations from a stored real drafting backend response", () => {
  const fixturePath = path.resolve(
    testDirectory,
    "../../backend/benchmarks/results/sri_lanka_golden_benchmark_20-5926f920caa4/ablation_dense_only.json",
  );
  const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  const draftingResult = fixture.results.find(
    (result) => result.mode === "drafting" && result.output?.sources?.length,
  );
  assert.ok(draftingResult, "Expected a drafting result with sources");

  const builder = new DocumentBuilder();
  const document = builder.fromMarkdown(
    draftingResult.output.markdown_content ?? draftingResult.output.answer,
    draftingResult.output.sources,
  );
  const citations = new CitationService().resolveCitations(
    document,
    draftingResult.output.sources,
  );
  const sourceIds = new Set(
    draftingResult.output.sources.map((source) => source.citation_id),
  );
  const expectedIds = new Set(
    Array.from(
      draftingResult.output.answer.matchAll(/(?:LAW|DOC)-\d+/g),
      (match) => `[${match[0]}]`,
    ).filter((citationId) => sourceIds.has(citationId)),
  );

  assert.ok(citations.length > 0);
  assert.ok(citations.some((citation) => citation.citationId === "[LAW-1]"));
  assert.deepEqual(
    new Set(citations.map((citation) => citation.citationId)),
    expectedIds,
  );
  assert.ok(citations.every((citation) => citation.status === "linked"));
  assert.ok(citations.every((citation) => citation.source?.title));
});
