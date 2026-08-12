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
  "../src/store/draftDocumentStore.ts",
);

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

function response(overrides = {}) {
  return {
    answer: "Fallback answer",
    markdown_content: "# Draft Agreement\n\nDraft body.",
    sources: [{ citation_id: "[LAW-1]", title: "Contract Law" }],
    ...overrides,
  };
}

function createHarness({ connectSSE, sendLegalQuery } = {}) {
  const activityCalls = [];
  const activity = {
    startStream: (sessionId) => activityCalls.push(["start", sessionId]),
    processEvent: (event) => activityCalls.push(["event", event.event_type]),
    endStream: () => activityCalls.push(["end"]),
    setError: (message) => activityCalls.push(["error", message]),
    reset: () => activityCalls.push(["reset"]),
  };
  let legacyCalls = 0;
  const legacy = async (...args) => {
    legacyCalls += 1;
    return sendLegalQuery ? sendLegalQuery(...args) : response();
  };
  const stream =
    connectSSE ??
    (async (options) => {
      options.onEvent({ event_type: "step_start" });
      options.onComplete(response());
    });

  class FakeDocumentBuilder {
    fromMarkdown(markdown, sources) {
      return { type: "doc", content: [{ type: "paragraph", markdown, sources }] };
    }
  }

  const store = loadTypeScriptModule(storeFilename, {
    "@/lib/api": { sendLegalQuery: legacy },
    "@/lib/drafting/documentBuilder": { DocumentBuilder: FakeDocumentBuilder },
    "@/lib/sseClient": {
      connectSSE: stream,
      isSSEEndpointUnavailableError: (error) =>
        error?.endpointUnavailable === true,
    },
    "@/store/activityStreamStore": {
      useActivityStreamStore: { getState: () => activity },
    },
  }).useDraftDocumentStore;

  return {
    store,
    activityCalls,
    legacyCalls: () => legacyCalls,
  };
}

test("draft generation consumes streamed activity and builds canonical state", async () => {
  const harness = createHarness();

  await harness.store.getState().startDraft("Draft an agreement", ["doc-1"]);

  const state = harness.store.getState();
  assert.equal(harness.legacyCalls(), 0);
  assert.equal(state.isLoading, false);
  assert.equal(state.error, null);
  assert.equal(state.title, "Draft Agreement");
  assert.equal(state.markdownContent, "# Draft Agreement\n\nDraft body.");
  assert.equal(state.sources[0].citation_id, "[LAW-1]");
  assert.equal(state.documentJson.type, "doc");
  assert.deepEqual(
    harness.activityCalls.map(([kind]) => kind),
    ["start", "event", "end"],
  );
});

test("draft generation falls back only when the stream endpoint is unavailable", async () => {
  const unavailable = Object.assign(new Error("Not found"), {
    endpointUnavailable: true,
  });
  const harness = createHarness({
    connectSSE: async () => {
      throw unavailable;
    },
    sendLegalQuery: async () => response({ markdown_content: "# Legacy Draft" }),
  });

  await harness.store.getState().startDraft("Draft", []);

  assert.equal(harness.legacyCalls(), 1);
  assert.equal(harness.store.getState().markdownContent, "# Legacy Draft");
  assert.deepEqual(
    harness.activityCalls.map(([kind]) => kind),
    ["start", "reset", "end"],
  );
});

test("runtime stream failures are surfaced and never execute a second graph", async () => {
  const harness = createHarness({
    connectSSE: async () => {
      throw new Error("Provider unavailable");
    },
  });

  await harness.store.getState().startDraft("Draft", []);

  assert.equal(harness.legacyCalls(), 0);
  assert.equal(harness.store.getState().isLoading, false);
  assert.equal(harness.store.getState().error, "Provider unavailable");
  assert.deepEqual(
    harness.activityCalls.map(([kind]) => kind),
    ["start", "error", "end"],
  );
});

test("reset aborts an in-flight draft without publishing a stale error", async () => {
  let observedSignal;
  const harness = createHarness({
    connectSSE: async (options) => {
      observedSignal = options.signal;
      await new Promise((_resolve, reject) => {
        options.signal.addEventListener("abort", () => {
          reject(new DOMException("Aborted", "AbortError"));
        });
      });
    },
  });

  const pending = harness.store.getState().startDraft("Draft", []);
  harness.store.getState().reset();
  await pending;

  assert.equal(observedSignal.aborted, true);
  assert.equal(harness.store.getState().isLoading, false);
  assert.equal(harness.store.getState().error, null);
  assert.equal(harness.store.getState().draftId, null);
  assert.ok(harness.activityCalls.some(([kind]) => kind === "reset"));
});
