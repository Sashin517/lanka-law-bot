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

const exportTypes = loadTypeScriptModule(
  path.resolve(
    testDirectory,
    "../src/lib/drafting/exportStrategies/types.ts",
  ),
);
const formattingModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/formatting.ts"),
);
const strategyDependencies = {
  "@/lib/drafting/exportStrategies/types": exportTypes,
  "@/lib/drafting/formatting": formattingModule,
};
const docxModule = loadTypeScriptModule(
  path.resolve(
    testDirectory,
    "../src/lib/drafting/exportStrategies/DocxExportStrategy.ts",
  ),
  strategyDependencies,
);
const pdfModule = loadTypeScriptModule(
  path.resolve(
    testDirectory,
    "../src/lib/drafting/exportStrategies/PdfExportStrategy.ts",
  ),
  strategyDependencies,
);
const exportServiceModule = loadTypeScriptModule(
  path.resolve(testDirectory, "../src/lib/drafting/exportService.ts"),
  {
    "@/lib/drafting/exportStrategies/DocxExportStrategy": docxModule,
    "@/lib/drafting/exportStrategies/PdfExportStrategy": pdfModule,
  },
);

const { DocxExportStrategy } = docxModule;
const { PdfExportStrategy, renderPdfHtml } = pdfModule;
const { ExportService, ExportStrategyFactory } = exportServiceModule;
const { withoutCitationMarks } = exportTypes;
const JSZip = nodeRequire("jszip");

const source = {
  citation_id: "[LAW-1]",
  title: "Data Protection Act",
  section: "Section 12",
  year: 2022,
  breadcrumb: null,
  excerpt: "Processing must be lawful.",
  page_start: 14,
  page_end: 15,
  reporter_citation: null,
  court: null,
};

const options = {
  format: "docx",
  includeMetadata: true,
  includeSources: true,
  includeDisclaimer: true,
  pageSize: "A4",
  margins: { top: 72, right: 72, bottom: 72, left: 72 },
};

const metadata = {
  title: "Privacy Agreement",
  author: "Attorney Example",
  date: "2026-08-10T00:00:00.000Z",
  versionNumber: 3,
};

function richDocument() {
  return {
    type: "doc",
    content: [
      {
        type: "heading",
        attrs: { level: 1 },
        content: [{ type: "text", text: "Privacy Agreement" }],
      },
      {
        type: "paragraph",
        attrs: {
          textAlign: "justify",
          indentLevel: 2,
          lineSpacing: 1.5,
          spacingBefore: 6,
          spacingAfter: 12,
        },
        content: [
          {
            type: "text",
            text: "The Controller",
            marks: [
              { type: "bold" },
              { type: "textStyle", attrs: { fontSize: 14 } },
            ],
          },
          { type: "text", text: " shall comply ", marks: [{ type: "italic" }] },
          {
            type: "text",
            text: "[LAW-1]",
            marks: [
              {
                type: "citationMark",
                attrs: { citationId: "[LAW-1]" },
              },
              {
                type: "editHighlight",
                attrs: { editType: "modification" },
              },
            ],
          },
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
                content: [{ type: "text", text: "Security obligation" }],
              },
            ],
          },
        ],
      },
      {
        type: "orderedList",
        content: [
          {
            type: "listItem",
            content: [
              {
                type: "paragraph",
                content: [{ type: "text", text: "Notify the authority" }],
              },
            ],
          },
        ],
      },
      {
        type: "blockquote",
        content: [
          {
            type: "paragraph",
            content: [{ type: "text", text: "Quoted authority" }],
          },
        ],
      },
      {
        type: "table",
        content: [
          {
            type: "tableRow",
            content: [
              {
                type: "tableHeader",
                content: [
                  {
                    type: "paragraph",
                    content: [{ type: "text", text: "Duty" }],
                  },
                ],
              },
              {
                type: "tableCell",
                content: [
                  {
                    type: "paragraph",
                    content: [{ type: "text", text: "Comply" }],
                  },
                ],
              },
            ],
          },
        ],
      },
    ],
  };
}

async function docxXml(blob, filename) {
  const zip = await JSZip.loadAsync(Buffer.from(await blob.arrayBuffer()));
  return zip.file(filename)?.async("string");
}

test("citation removal is recursive and does not mutate the accepted version", () => {
  const document = richDocument();
  document.content[1].content.push(
    { type: "text", text: ", " },
    {
      type: "text",
      text: "[DOC-2]",
      marks: [
        {
          type: "citationMark",
          attrs: { citationId: "[DOC-2]" },
        },
      ],
    },
  );

  const exported = withoutCitationMarks(document);

  assert.notStrictEqual(exported, document);
  assert.match(JSON.stringify(document), /citationMark/);
  assert.doesNotMatch(JSON.stringify(exported), /citationMark|\[(?:LAW|DOC)-\d+\]/);
  assert.equal(
    exported.content[1].content.map((node) => node.text ?? "").join(""),
    "The Controller shall comply ",
  );
});

test("DOCX preserves legal formatting and sources while removing citations", async () => {
  const blob = await new DocxExportStrategy().export(
    richDocument(),
    [source],
    options,
    metadata,
  );
  const documentXml = await docxXml(blob, "word/document.xml");
  const numberingXml = await docxXml(blob, "word/numbering.xml");
  const coreXml = await docxXml(blob, "docProps/core.xml");

  assert.ok(blob.size > 1_000);
  assert.match(documentXml, /Heading1/);
  assert.match(documentXml, /<w:b\/>/);
  assert.match(documentXml, /<w:i\/>/);
  assert.match(documentXml, /<w:sz w:val="28"\/>/);
  assert.match(documentXml, /<w:jc w:val="both"\/>/);
  assert.match(documentXml, /<w:ind w:left="1440"\/>/);
  assert.match(documentXml, /w:before="120"/);
  assert.match(documentXml, /w:after="240"/);
  assert.match(documentXml, /w:line="360"/);
  assert.match(documentXml, /<w:tbl>/);
  assert.doesNotMatch(documentXml, /footnoteReference/);
  assert.doesNotMatch(documentXml, /\[LAW-1\]/);
  assert.match(documentXml, /Sources/);
  assert.match(documentXml, /Data Protection Act/);
  assert.match(documentXml, /Legal Disclaimer/);
  assert.doesNotMatch(documentXml, /editHighlight/);
  assert.match(numberingXml, /w:numFmt w:val="decimal"/);
  assert.match(numberingXml, /w:numFmt w:val="bullet"/);
  assert.match(coreXml, /Privacy Agreement/);
});

test("DOCX respects disabled metadata, sources, and disclaimer options", async () => {
  const blob = await new DocxExportStrategy().export(
    richDocument(),
    [source],
    {
      ...options,
      includeMetadata: false,
      includeSources: false,
      includeDisclaimer: false,
    },
    metadata,
  );
  const documentXml = await docxXml(blob, "word/document.xml");

  assert.doesNotMatch(documentXml, /Prepared by Attorney Example/);
  assert.doesNotMatch(documentXml, /Legal Disclaimer/);
  assert.doesNotMatch(documentXml, /footnoteReference/);
});

test("PDF HTML is print-safe, escaped, and removes citations", () => {
  const document = richDocument();
  document.content.push({
    type: "paragraph",
    content: [{ type: "text", text: "<script>alert('x')</script>" }],
  });
  const html = renderPdfHtml(
    document,
    [source],
    { ...options, format: "pdf", pageSize: "Letter" },
    metadata,
  );

  assert.match(html, /data-page-size="Letter"/);
  assert.match(html, /<h1>Privacy Agreement<\/h1>/);
  assert.match(
    html,
    /<strong><span data-font-size="14" style="font-size:14pt">The Controller<\/span><\/strong>/,
  );
  assert.match(html, /data-font-size="14" style="font-size:14pt"/);
  assert.match(
    html,
    /text-align:justify;margin-left:72pt;line-height:1.5;margin-top:6pt;margin-bottom:12pt/,
  );
  assert.match(html, /<table>/);
  assert.doesNotMatch(html, /class="citation"/);
  assert.doesNotMatch(html, /\[LAW-1\]/);
  assert.match(html, /Data Protection Act/);
  assert.match(html, /Legal Disclaimer/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>alert/);
  assert.doesNotMatch(html, /editHighlight/);
});

test("PDF strategy fails clearly during SSR without importing its browser renderer", async () => {
  await assert.rejects(
    () =>
      new PdfExportStrategy().export(
        richDocument(),
        [source],
        { ...options, format: "pdf" },
        metadata,
      ),
    /only available in a browser session/,
  );
});

test("PDF strategy passes populated HTML directly to the renderer", async () => {
  const rendererCalls = {};
  const worker = {
    set(value) {
      rendererCalls.options = value;
      return this;
    },
    from(value, type) {
      rendererCalls.source = value;
      rendererCalls.sourceType = type;
      return this;
    },
    toPdf() {
      return this;
    },
    outputPdf(type) {
      rendererCalls.outputType = type;
      return Promise.resolve(
        new Blob(["rendered-pdf"], { type: "application/pdf" }),
      );
    },
  };
  const browserPdfModule = loadTypeScriptModule(
    path.resolve(
      testDirectory,
      "../src/lib/drafting/exportStrategies/PdfExportStrategy.ts",
    ),
    {
      ...strategyDependencies,
      "html2pdf.js": {
        __esModule: true,
        default: () => worker,
      },
    },
  );

  globalThis.document = {};
  try {
    const blob = await new browserPdfModule.PdfExportStrategy().export(
      richDocument(),
      [source],
      { ...options, format: "pdf" },
      metadata,
    );

    assert.equal(typeof rendererCalls.source, "string");
    assert.match(rendererCalls.source, /Privacy Agreement/);
    assert.match(rendererCalls.source, /The Controller/);
    assert.doesNotMatch(rendererCalls.source, /\[LAW-1\]/);
    assert.equal(rendererCalls.outputType, "blob");
    assert.ok(blob.size > 0);
  } finally {
    delete globalThis.document;
  }
});

test("ExportService uses the immutable version snapshot and a safe versioned filename", async () => {
  const calls = [];
  const downloads = [];
  const strategy = {
    async export(document, sources, exportOptions, exportMetadata) {
      calls.push({ document, sources, exportOptions, exportMetadata });
      return new Blob(["artifact"], { type: "application/test" });
    },
  };
  const service = new ExportService(
    () => strategy,
    async (blob, filename) => downloads.push({ blob, filename }),
  );
  const version = {
    id: "version-3",
    versionNumber: 3,
    label: "Version 3",
    content: richDocument(),
    sources: [source],
    createdAt: metadata.date,
    createdBy: "user",
    editSummary: "Accepted edit",
    parentVersionId: "version-2",
  };

  const artifact = await service.exportDocument({
    version,
    options,
    title: "Agreement: Privacy / 2026",
    author: "Attorney Example",
  });

  assert.strictEqual(calls[0].document, version.content);
  assert.strictEqual(calls[0].sources, version.sources);
  assert.equal(calls[0].exportMetadata.versionNumber, 3);
  assert.equal(artifact.versionId, "version-3");
  assert.equal(artifact.filename, "Agreement-Privacy-2026-v3.docx");
  assert.equal(downloads[0].filename, artifact.filename);
});

test("ExportStrategyFactory returns the requested strategy", () => {
  assert.ok(ExportStrategyFactory.create("docx") instanceof DocxExportStrategy);
  assert.ok(ExportStrategyFactory.create("pdf") instanceof PdfExportStrategy);
});
