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
  "../src/store/activityStreamStore.ts",
);

function loadStore() {
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
  return loaded.exports.useActivityStreamStore;
}

function event(eventType, overrides = {}) {
  return {
    event_type: eventType,
    session_id: "backend-session",
    event_id: `${eventType}-default`,
    timestamp: 100,
    step_name: "router",
    step_label: "Analysing legal question",
    step_status: "running",
    detail: "",
    metadata: {},
    ...overrides,
  };
}

test("store applies the complete step lifecycle and ignores replayed events", () => {
  const store = loadStore();
  const actions = store.getState();
  actions.startStream("client-session");
  actions.processEvent(event("stream_start", { event_id: "1" }));
  actions.processEvent(event("step_start", { event_id: "2" }));
  const detail = event("step_detail", {
    event_id: "3",
    detail: "Selected deep research route",
    metadata: { route: "deep_research" },
  });
  actions.processEvent(detail);
  actions.processEvent(detail);
  actions.processEvent(
    event("step_done", {
      event_id: "4",
      timestamp: 104,
      step_label: "Routing complete",
      step_status: "done",
    }),
  );
  actions.processEvent(
    event("final", {
      event_id: "5",
      timestamp: 105,
      step_name: "formatter",
      step_status: "done",
      final_response: { answer: "Result" },
    }),
  );

  const state = store.getState();
  assert.equal(state.sessionId, "backend-session");
  assert.equal(state.isStreaming, false);
  assert.equal(state.error, null);
  assert.equal(state.steps.length, 1);
  assert.equal(state.steps[0].status, "done");
  assert.equal(state.steps[0].label, "Routing complete");
  assert.deepEqual(state.steps[0].details, ["Selected deep research route"]);
  assert.deepEqual(state.steps[0].metadata, { route: "deep_research" });
  assert.equal(state.steps[0].completedAt, 104);
});

test("sources and generated plans retain structured metadata", () => {
  const store = loadStore();
  const actions = store.getState();
  actions.startStream("client-session");
  actions.processEvent(
    event("step_start", {
      event_id: "plan-1",
      step_name: "supervisor",
      step_label: "Planning execution",
    }),
  );
  actions.processEvent(
    event("plan_generated", {
      event_id: "plan-2",
      step_name: "supervisor",
      metadata: { plan_type: "planned", planned_steps: ["retrieval"] },
    }),
  );
  actions.processEvent(
    event("sources_found", {
      event_id: "sources-1",
      step_name: "retrieval",
      step_label: "Found 2 authorities",
      step_status: "done",
      metadata: { count: 2, titles: ["Authority A", null, "Authority B"] },
    }),
  );

  const [supervisor, sources] = store.getState().steps;
  assert.deepEqual(supervisor.metadata, {
    plan_type: "planned",
    planned_steps: ["retrieval"],
  });
  assert.equal(sources.stepName, "sources");
  assert.equal(sources.status, "done");
  assert.deepEqual(sources.details, ["Authority A", "Authority B"]);
  assert.equal(sources.completedAt, 100);
});

test("step and stream failures become visible terminal activity", () => {
  const store = loadStore();
  const actions = store.getState();
  actions.startStream("client-session");
  actions.processEvent(
    event("step_start", { event_id: "error-start", step_name: "grounding" }),
  );
  actions.processEvent(
    event("step_error", {
      event_id: "error-step",
      step_name: "grounding",
      step_status: "error",
      detail: "Grounding check failed",
    }),
  );
  actions.processEvent(
    event("error", {
      event_id: "error-stream",
      step_name: "stream",
      step_status: "error",
      detail: "Workflow stopped",
    }),
  );

  const state = store.getState();
  assert.equal(state.isStreaming, false);
  assert.equal(state.error, "Workflow stopped");
  assert.deepEqual(state.steps.map((step) => step.status), ["error", "error"]);
  assert.deepEqual(state.steps[0].details, ["Grounding check failed"]);
  assert.deepEqual(state.steps[1].details, ["Workflow stopped"]);
});

test("reset clears activity, session, error, and deduplication history", () => {
  const store = loadStore();
  const actions = store.getState();
  const startEvent = event("step_start", { event_id: "reusable-id" });
  actions.startStream("first");
  actions.processEvent(startEvent);
  actions.setError("Network failed");
  actions.reset();

  assert.deepEqual(store.getState().steps, []);
  assert.equal(store.getState().sessionId, null);
  assert.equal(store.getState().error, null);
  assert.equal(store.getState().isStreaming, false);

  store.getState().startStream("second");
  store.getState().processEvent(startEvent);
  assert.equal(store.getState().steps.length, 1);
});
