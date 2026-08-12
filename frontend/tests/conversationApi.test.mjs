import assert from "node:assert/strict";
import fs from "node:fs";
import Module, { createRequire } from "node:module";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import ts from "typescript";

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const nodeRequire = createRequire(import.meta.url);
const apiFilename = path.resolve(
  testDirectory,
  "../src/lib/conversationApi.ts",
);
const sseFilename = path.resolve(testDirectory, "../src/lib/sseClient.ts");
const streamingTypesFilename = path.resolve(
  testDirectory,
  "../src/types/streaming.ts",
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

function loadApi(auth = { currentUser: null }) {
  const streamingTypes = loadTypeScriptModule(streamingTypesFilename);
  const sseClient = loadTypeScriptModule(sseFilename, {
    "@/lib/api": { API_BASE_URL: "https://unused.example.test" },
    "@/types/streaming": streamingTypes,
  });
  return loadTypeScriptModule(apiFilename, {
    "@/lib/firebase/firebase": { auth },
    "@/lib/sseClient": sseClient,
  });
}

function jsonResponse(body, status = 200, statusText = "") {
  return new Response(JSON.stringify(body), {
    status,
    statusText,
    headers: { "Content-Type": "application/json" },
  });
}

function streamEvent(eventType, overrides = {}) {
  return {
    event_type: eventType,
    session_id: "conversation-stream-1",
    event_id: `conversation-stream-1:${eventType}`,
    timestamp: 1_786_500_000,
    step_name: "router",
    step_label: "Analyzing request",
    step_status: eventType === "final" ? "done" : "running",
    detail: "",
    metadata: {},
    ...overrides,
  };
}

function sseResponse(events) {
  const body = events
    .map(
      (event) =>
        `id: ${event.event_id}\nevent: ${event.event_type}\ndata: ${JSON.stringify(event)}\n\n`,
    )
    .join("");
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

test("list facade injects Firebase bearer token and cursor parameters", async () => {
  const { ConversationApiClient } = loadApi();
  const tokenCalls = [];
  const requests = [];
  const client = new ConversationApiClient(
    "https://api.example.test/",
    {
      async getToken(forceRefresh) {
        tokenCalls.push(forceRefresh);
        return "valid-id-token";
      },
    },
    async (url, options) => {
      requests.push({ url, options });
      return jsonResponse({ conversations: [], next_cursor: null });
    },
  );

  const result = await client.listConversations("cursor+/=", 25);

  assert.deepEqual(result, { conversations: [], next_cursor: null });
  assert.deepEqual(tokenCalls, [false]);
  assert.equal(
    requests[0].url,
    "https://api.example.test/api/conversations?limit=25&cursor=cursor%2B%2F%3D",
  );
  const headers = new Headers(requests[0].options.headers);
  assert.equal(headers.get("Authorization"), "Bearer valid-id-token");
  assert.equal(headers.get("Accept"), "application/json");
  assert.equal(headers.get("Content-Type"), null);
  assert.equal(requests[0].options.cache, "no-store");
});

test("send facade encodes IDs and preserves the backend request contract", async () => {
  const { ConversationApiClient } = loadApi();
  const requests = [];
  const responseBody = {
    user_message: { id: "user-1" },
    assistant_message: { id: "assistant-1" },
    response: { answer: "Answer" },
  };
  const client = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async (url, options) => {
      requests.push({ url, options });
      return jsonResponse(responseBody);
    },
  );

  const result = await client.sendMessage(
    "conversation/one",
    "Question",
    "reasoning",
    ["doc-1"],
    [{ document_id: "doc-1", filename: "law.pdf", status: "completed" }],
  );

  assert.deepEqual(result, responseBody);
  assert.equal(
    requests[0].url,
    "https://api.example.test/api/conversations/conversation%2Fone/messages",
  );
  assert.equal(requests[0].options.method, "POST");
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    content: "Question",
    query_mode: "reasoning",
    document_ids: ["doc-1"],
    attachments: [
      { document_id: "doc-1", filename: "law.pdf", status: "completed" },
    ],
  });
  assert.equal(
    new Headers(requests[0].options.headers).get("Content-Type"),
    "application/json",
  );
});

test("streaming send authenticates, forwards activity, and returns persisted turns", async () => {
  const { ConversationApiClient } = loadApi();
  const requests = [];
  const received = [];
  const finalResponse = {
    user_message: { id: "user-1" },
    assistant_message: { id: "assistant-1" },
    response: { answer: "Persisted streamed answer" },
  };
  const client = new ConversationApiClient(
    "https://api.example.test/",
    { getToken: async () => "stream-token" },
    async (url, options) => {
      requests.push({ url, options });
      return sseResponse([
        streamEvent("step_start"),
        streamEvent("final", {
          event_id: "conversation-stream-1:final",
          step_name: "conversation",
          final_response: finalResponse,
        }),
      ]);
    },
  );

  const result = await client.sendMessageStream(
    "conversation/one",
    "Question",
    "reasoning",
    ["doc-1"],
    [{ document_id: "doc-1", filename: "law.pdf", status: "completed" }],
    { onEvent: (event) => received.push(event.event_type) },
  );

  assert.deepEqual(result, finalResponse);
  assert.deepEqual(received, ["step_start", "final"]);
  assert.equal(
    requests[0].url,
    "https://api.example.test/api/conversations/conversation%2Fone/messages/stream",
  );
  const headers = new Headers(requests[0].options.headers);
  assert.equal(headers.get("Authorization"), "Bearer stream-token");
  assert.equal(headers.get("Accept"), "text/event-stream");
  assert.deepEqual(JSON.parse(requests[0].options.body), {
    content: "Question",
    query_mode: "reasoning",
    document_ids: ["doc-1"],
    attachments: [
      { document_id: "doc-1", filename: "law.pdf", status: "completed" },
    ],
  });
});

test("streaming send refreshes one expired token before consuming events", async () => {
  const { ConversationApiClient } = loadApi();
  const tokenCalls = [];
  const authorizationHeaders = [];
  let requestCount = 0;
  const finalResponse = {
    user_message: { id: "user-1" },
    assistant_message: { id: "assistant-1" },
    response: { answer: "Answer" },
  };
  const client = new ConversationApiClient(
    "https://api.example.test",
    {
      async getToken(forceRefresh) {
        tokenCalls.push(forceRefresh);
        return forceRefresh ? "fresh-token" : "cached-token";
      },
    },
    async (_url, options) => {
      requestCount += 1;
      authorizationHeaders.push(
        new Headers(options.headers).get("Authorization"),
      );
      return requestCount === 1
        ? jsonResponse({ detail: "Expired" }, 401)
        : sseResponse([
            streamEvent("final", {
              final_response: finalResponse,
            }),
          ]);
    },
  );

  const result = await client.sendMessageStream(
    "conversation-1",
    "Question",
    "quick_qa",
    [],
    [],
    { onEvent: () => undefined },
  );

  assert.deepEqual(result, finalResponse);
  assert.deepEqual(tokenCalls, [false, true]);
  assert.deepEqual(authorizationHeaders, [
    "Bearer cached-token",
    "Bearer fresh-token",
  ]);
});

test("only an unavailable streaming route is classified for legacy fallback", async () => {
  const {
    ConversationApiClient,
    ConversationStreamError,
    isConversationStreamUnavailableError,
  } = loadApi();
  const client = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () => jsonResponse({ detail: "Not Found" }, 404),
  );

  await assert.rejects(
    () =>
      client.sendMessageStream(
        "conversation-1",
        "Question",
        "quick_qa",
        [],
        [],
        { onEvent: () => undefined },
      ),
    (error) => {
      assert.ok(error instanceof ConversationStreamError);
      assert.equal(error.status, 404);
      assert.equal(error.endpointUnavailable, true);
      assert.equal(isConversationStreamUnavailableError(error), true);
      return true;
    },
  );
});

test("one 401 response forces token refresh and retries once", async () => {
  const { ConversationApiClient } = loadApi();
  const refreshCalls = [];
  const authorizationHeaders = [];
  let requestCount = 0;
  const client = new ConversationApiClient(
    "https://api.example.test",
    {
      async getToken(forceRefresh) {
        refreshCalls.push(forceRefresh);
        return forceRefresh ? "fresh-token" : "cached-token";
      },
    },
    async (_url, options) => {
      requestCount += 1;
      authorizationHeaders.push(
        new Headers(options.headers).get("Authorization"),
      );
      return requestCount === 1
        ? jsonResponse({ detail: "Authentication token expired." }, 401)
        : jsonResponse({ conversations: [], next_cursor: null });
    },
  );

  await client.listConversations();

  assert.deepEqual(refreshCalls, [false, true]);
  assert.deepEqual(authorizationHeaders, [
    "Bearer cached-token",
    "Bearer fresh-token",
  ]);
  assert.equal(requestCount, 2);
});

test("typed API errors retain status and backend details", async () => {
  const { ConversationApiClient, ConversationApiError } = loadApi();
  const client = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () => jsonResponse({ detail: "Conversation not found." }, 404),
  );

  await assert.rejects(
    () => client.getConversation("missing"),
    (error) => {
      assert.ok(error instanceof ConversationApiError);
      assert.equal(error.status, 404);
      assert.equal(error.message, "Conversation not found.");
      assert.deepEqual(error.details, { detail: "Conversation not found." });
      return true;
    },
  );
});

test("validation error arrays are converted into a useful client message", async () => {
  const { ConversationApiClient } = loadApi();
  const client = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () =>
      jsonResponse(
        {
          detail: [
            { loc: ["body", "title"], msg: "title must not be blank" },
            { loc: ["body", "query_mode"], msg: "invalid query mode" },
          ],
        },
        422,
      ),
  );

  await assert.rejects(
    () => client.createConversation(""),
    (error) => {
      assert.equal(
        error.message,
        "title must not be blank; invalid query mode",
      );
      return true;
    },
  );
});

test("network and malformed success responses have stable errors", async () => {
  const { ConversationApiClient, ConversationApiError } = loadApi();
  const networkClient = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () => {
      throw new TypeError("private transport detail");
    },
  );
  await assert.rejects(
    () => networkClient.listConversations(),
    (error) => {
      assert.ok(error instanceof ConversationApiError);
      assert.equal(error.status, 0);
      assert.equal(error.message, "Unable to reach the conversation service");
      return true;
    },
  );

  const malformedClient = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () => new Response("not-json", { status: 200 }),
  );
  await assert.rejects(
    () => malformedClient.listConversations(),
    (error) => {
      assert.ok(error instanceof ConversationApiError);
      assert.equal(error.status, 200);
      assert.equal(
        error.message,
        "Conversation service returned an invalid response",
      );
      return true;
    },
  );
});

test("client-side constraints reject invalid IDs and page sizes before fetch", async () => {
  const { ConversationApiClient } = loadApi();
  let requestCount = 0;
  const client = new ConversationApiClient(
    "https://api.example.test",
    { getToken: async () => "token" },
    async () => {
      requestCount += 1;
      return jsonResponse({});
    },
  );

  assert.throws(() => client.listConversations(null, 101), RangeError);
  assert.throws(
    () => client.listMessages("conversation-1", null, 0),
    RangeError,
  );
  assert.throws(() => client.getConversation("  "), TypeError);
  assert.equal(requestCount, 0);
});

test("default facade reads Firebase currentUser and fails closed when signed out", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  const auth = {
    currentUser: {
      async getIdToken(forceRefresh) {
        assert.equal(forceRefresh, false);
        return "firebase-user-token";
      },
    },
  };
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return jsonResponse({
      id: "conversation-1",
      title: "New Chat",
      query_mode: "quick_qa",
      message_count: 0,
      last_message_preview: "",
      created_at: "2026-08-12T00:00:00Z",
      updated_at: "2026-08-12T00:00:00Z",
    });
  };

  try {
    const api = loadApi(auth);
    await api.createConversation();
    assert.equal(
      new Headers(requests[0].options.headers).get("Authorization"),
      "Bearer firebase-user-token",
    );

    auth.currentUser = null;
    await assert.rejects(
      () => api.createConversation(),
      (error) => error.status === 401 && error.message === "Not authenticated",
    );
    assert.equal(requests.length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
