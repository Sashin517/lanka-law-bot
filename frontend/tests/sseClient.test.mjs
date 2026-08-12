import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);
const clientFilename = path.resolve(testDirectory, "../src/lib/sseClient.ts");
const typesFilename = path.resolve(testDirectory, "../src/types/streaming.ts");

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

function loadClient() {
  const streamingTypes = loadTypeScriptModule(typesFilename);
  return loadTypeScriptModule(clientFilename, {
    "@/lib/api": { API_BASE_URL: "https://api.example.test/" },
    "@/types/streaming": streamingTypes,
  });
}

function streamEvent(eventType, overrides = {}) {
  return {
    event_type: eventType,
    session_id: "session-1",
    event_id: `${eventType}-1`,
    timestamp: 1_786_500_000,
    step_name: "router",
    step_label: "Analysing request",
    step_status: eventType === "final" ? "done" : "running",
    detail: "",
    metadata: {},
    ...overrides,
  };
}

function eventFrame(event, newline = "\n") {
  return [
    `id: ${event.event_id}`,
    `event: ${event.event_type}`,
    `data: ${JSON.stringify(event)}`,
    "",
    "",
  ].join(newline);
}

function chunkedResponse(chunks, contentType = "text/event-stream; charset=utf-8") {
  const encoder = new TextEncoder();
  return new Response(
    new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
    { status: 200, headers: { "Content-Type": contentType } },
  );
}

test("POST client parses chunked CRLF frames, ignores comments and deduplicates IDs", async () => {
  const { connectSSE } = loadClient();
  const originalFetch = globalThis.fetch;
  const requests = [];
  const received = [];
  let completed = null;
  const start = streamEvent("stream_start");
  const final = streamEvent("final", {
    event_id: "final-1",
    step_name: "formatter",
    final_response: { answer: "Complete" },
  });
  const payload = `${eventFrame(start, "\r\n")}: heartbeat\r\n\r\n${eventFrame(start)}${eventFrame(final)}`;

  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return chunkedResponse([
      payload.slice(0, 19),
      payload.slice(19, 73),
      payload.slice(73),
    ]);
  };

  try {
    await connectSSE({
      endpoint: "/api/search/stream",
      payload: { question: "What is the law?" },
      onEvent: (event) => received.push(event.event_type),
      onComplete: (response) => {
        completed = response;
      },
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(received, ["stream_start", "final"]);
  assert.deepEqual(completed, { answer: "Complete" });
  assert.equal(requests[0].url, "https://api.example.test/api/search/stream");
  assert.equal(requests[0].options.method, "POST");
  assert.equal(requests[0].options.cache, "no-store");
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    question: "What is the law?",
  });
  const headers = new Headers(requests[0].options.headers);
  assert.equal(headers.get("Accept"), "text/event-stream");
  assert.equal(headers.get("Content-Type"), "application/json");
});

test("malformed and schema-invalid frames are skipped without stopping the stream", async () => {
  const { connectSSE } = loadClient();
  const originalFetch = globalThis.fetch;
  const received = [];
  const final = streamEvent("final", {
    event_id: "final-valid",
    final_response: { answer: "Still complete" },
  });
  const invalidSchema = { event_type: "step_start", session_id: "partial" };

  globalThis.fetch = async () =>
    chunkedResponse([
      "event: step_start\ndata: {broken-json}\n\n",
      `event: step_start\ndata: ${JSON.stringify(invalidSchema)}\n\n`,
      eventFrame(final),
    ]);

  try {
    await connectSSE({
      endpoint: "/api/search/stream",
      payload: {},
      onEvent: (event) => received.push(event.event_type),
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(received, ["final"]);
});

test("application error events are delivered to the store and reported once", async () => {
  const { connectSSE } = loadClient();
  const originalFetch = globalThis.fetch;
  const received = [];
  const errors = [];
  const failure = streamEvent("error", {
    event_id: "error-1",
    step_name: "stream",
    step_label: "Error occurred",
    step_status: "error",
    detail: "Graph execution failed",
  });
  globalThis.fetch = async () => chunkedResponse([eventFrame(failure)]);

  try {
    await connectSSE({
      endpoint: "/api/search/stream",
      payload: {},
      onEvent: (event) => received.push(event.event_type),
      onError: (error) => errors.push(error.message),
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(received, ["error"]);
  assert.deepEqual(errors, ["Graph execution failed"]);
});

test("retry is opt-in and sends the last event ID to a resumable endpoint", async () => {
  const { connectSSE } = loadClient();
  const originalFetch = globalThis.fetch;
  const requests = [];
  const detail = streamEvent("step_detail", { event_id: "session-1:4" });
  const final = streamEvent("final", {
    event_id: "session-1:5",
    final_response: { answer: "Resumed" },
  });

  globalThis.fetch = async (_url, options) => {
    requests.push(options);
    return requests.length === 1
      ? chunkedResponse([eventFrame(detail)])
      : chunkedResponse([eventFrame(detail), eventFrame(final)]);
  };

  try {
    await connectSSE({
      endpoint: "/api/resumable/stream",
      payload: {},
      reconnect: { maxAttempts: 1, delayMs: 0 },
      onEvent: () => undefined,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(requests.length, 2);
  assert.equal(
    new Headers(requests[1].headers).get("Last-Event-ID"),
    "session-1:4",
  );
});

test("abort is a normal terminal condition and does not call onError", async () => {
  const { connectSSE } = loadClient();
  const originalFetch = globalThis.fetch;
  const controller = new AbortController();
  let errorCalls = 0;

  globalThis.fetch = async (_url, options) =>
    new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => {
        reject(new DOMException("Aborted", "AbortError"));
      });
    });

  try {
    const connection = connectSSE({
      endpoint: "/api/search/stream",
      payload: {},
      signal: controller.signal,
      onEvent: () => undefined,
      onError: () => {
        errorCalls += 1;
      },
    });
    controller.abort();
    await connection;
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(errorCalls, 0);
});
