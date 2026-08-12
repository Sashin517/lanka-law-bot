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
  "../src/store/conversationStore.ts",
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

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function conversation(id, overrides = {}) {
  return {
    id,
    title: `Conversation ${id}`,
    query_mode: "quick_qa",
    message_count: 0,
    last_message_preview: "",
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    ...overrides,
  };
}

function message(id, role, content, sequenceNumber) {
  return {
    id,
    role,
    content,
    markdown_content: null,
    confidence: null,
    disclaimer: null,
    sequence_number: sequenceNumber,
    query_mode: role === "user" ? "quick_qa" : null,
    citations: [],
    attachments: [],
    created_at: `2026-08-12T00:00:0${sequenceNumber}Z`,
  };
}

function createApi(overrides = {}) {
  return {
    createConversation: async () => conversation("created"),
    deleteConversation: async () => undefined,
    listConversations: async () => ({ conversations: [], next_cursor: null }),
    listMessages: async () => ({ messages: [], next_cursor: null }),
    renameConversation: async () => undefined,
    sendMessage: async () => ({
      user_message: message("user-1", "user", "Question", 0),
      assistant_message: message("assistant-1", "assistant", "Answer", 1),
      response: { answer: "Answer" },
    }),
    ...overrides,
  };
}

function loadStore(api = createApi()) {
  return loadTypeScriptModule(storeFilename, {
    "@/lib/conversationApi": api,
  }).useConversationStore;
}

test("conversation pagination performs stable ID-keyed merging", async () => {
  const calls = [];
  const first = conversation("one", { title: "Original" });
  const api = createApi({
    async listConversations(cursor) {
      calls.push(cursor);
      return cursor === null
        ? { conversations: [first, first], next_cursor: "page-2" }
        : {
            conversations: [
              conversation("one", { title: "Updated" }),
              conversation("two"),
            ],
            next_cursor: null,
          };
    },
  });
  const store = loadStore(api);

  await store.getState().loadConversations();
  assert.deepEqual(store.getState().conversations.map((item) => item.id), ["one"]);
  assert.equal(store.getState().hasMoreConversations, true);

  await store.getState().loadMoreConversations();
  assert.deepEqual(store.getState().conversations.map((item) => item.id), [
    "one",
    "two",
  ]);
  assert.equal(store.getState().conversations[0].title, "Updated");
  assert.equal(store.getState().hasMoreConversations, false);
  assert.deepEqual(calls, [null, "page-2"]);
});

test("out-of-order conversation selection cannot overwrite active messages", async () => {
  const requests = new Map([
    ["one", deferred()],
    ["two", deferred()],
  ]);
  const store = loadStore(
    createApi({
      listMessages: async (conversationId) => requests.get(conversationId).promise,
    }),
  );

  const selectOne = store.getState().selectConversation("one");
  const selectTwo = store.getState().selectConversation("two");
  requests.get("two").resolve({
    messages: [message("two-message", "assistant", "Second", 0)],
    next_cursor: null,
  });
  await selectTwo;
  requests.get("one").resolve({
    messages: [message("one-message", "assistant", "First", 0)],
    next_cursor: null,
  });
  await selectOne;

  assert.equal(store.getState().activeConversationId, "two");
  assert.deepEqual(store.getState().messages.map((item) => item.id), [
    "two-message",
  ]);
  assert.equal(store.getState().isMessagesLoading, false);
});

test("message pagination appends without duplicating cursor-boundary records", async () => {
  const firstMessage = message("one", "user", "First", 0);
  const api = createApi({
    async listMessages(_conversationId, cursor) {
      return cursor === null
        ? { messages: [firstMessage], next_cursor: "message-page-2" }
        : {
            messages: [
              { ...firstMessage, content: "First updated" },
              message("two", "assistant", "Second", 1),
            ],
            next_cursor: null,
          };
    },
  });
  const store = loadStore(api);

  await store.getState().selectConversation("conversation-1");
  store.setState({
    messages: [
      ...store.getState().messages,
      message("newest", "assistant", "Newest reply", 3),
    ],
  });
  await store.getState().loadMoreMessages();

  assert.deepEqual(store.getState().messages.map((item) => item.id), [
    "one",
    "two",
    "newest",
  ]);
  assert.equal(store.getState().messages[0].content, "First updated");
  assert.equal(store.getState().hasMoreMessages, false);
});

test("new conversation becomes active and duplicate creation is guarded", async () => {
  const createRequest = deferred();
  const calls = [];
  const store = loadStore(
    createApi({
      async createConversation(title, queryMode) {
        calls.push({ title, queryMode });
        return createRequest.promise;
      },
    }),
  );

  const creation = store.getState().newConversation("reasoning");
  await assert.rejects(
    () => store.getState().newConversation(),
    /already being created/,
  );
  createRequest.resolve(conversation("created", { query_mode: "reasoning" }));

  assert.equal(await creation, "created");
  assert.equal(store.getState().activeConversationId, "created");
  assert.equal(store.getState().isCreating, false);
  assert.deepEqual(calls, [{ title: "New Chat", queryMode: "reasoning" }]);
});

test("send appends persisted turns and promotes updated conversation", async () => {
  const calls = [];
  const store = loadStore(
    createApi({
      async sendMessage(...args) {
        calls.push(args);
        return {
          user_message: message("user-1", "user", "Question", 0),
          assistant_message: message(
            "assistant-1",
            "assistant",
            "Persisted answer",
            1,
          ),
          response: { answer: "Persisted answer" },
        };
      },
    }),
  );
  store.setState({
    conversations: [conversation("other"), conversation("active")],
    activeConversationId: "active",
  });

  await store.getState().send(
    "Question",
    "deep_research",
    ["doc-1"],
    [{ document_id: "doc-1", filename: "law.pdf", status: "completed" }],
  );

  assert.deepEqual(store.getState().messages.map((item) => item.id), [
    "user-1",
    "assistant-1",
  ]);
  assert.deepEqual(store.getState().conversations.map((item) => item.id), [
    "active",
    "other",
  ]);
  assert.equal(store.getState().conversations[0].message_count, 2);
  assert.equal(
    store.getState().conversations[0].last_message_preview,
    "Persisted answer",
  );
  assert.deepEqual(calls[0].slice(0, 4), [
    "active",
    "Question",
    "deep_research",
    ["doc-1"],
  ]);
});

test("send immediately displays optimistic user message while awaiting response", async () => {
  const request = deferred();
  const store = loadStore(
    createApi({ sendMessage: async () => request.promise }),
  );
  store.setState({
    conversations: [conversation("active")],
    activeConversationId: "active",
  });

  const sendPromise = store.getState().send("Immediate Question");

  assert.equal(store.getState().isSending, true);
  assert.equal(store.getState().messages.length, 1);
  assert.equal(store.getState().messages[0].role, "user");
  assert.equal(store.getState().messages[0].content, "Immediate Question");

  request.resolve({
    user_message: message("user-1", "user", "Immediate Question", 0),
    assistant_message: message("assistant-1", "assistant", "Answer", 1),
    response: { answer: "Answer" },
  });
  await sendPromise;

  assert.equal(store.getState().isSending, false);
  assert.deepEqual(store.getState().messages.map((item) => item.id), [
    "user-1",
    "assistant-1",
  ]);
});

test("stopSending aborts the active request and keeps the submitted message", async () => {
  let requestSignal;
  const store = loadStore(
    createApi({
      sendMessage: async (...args) => {
        requestSignal = args[5].signal;
        return new Promise((_resolve, reject) => {
          requestSignal.addEventListener("abort", () => {
            reject(new DOMException("The operation was aborted", "AbortError"));
          });
        });
      },
    }),
  );
  store.setState({
    conversations: [conversation("active")],
    activeConversationId: "active",
  });

  const sending = store.getState().send("Stop this question");
  assert.equal(store.getState().isSending, true);

  store.getState().stopSending();
  await sending;

  assert.equal(requestSignal.aborted, true);
  assert.equal(store.getState().isSending, false);
  assert.equal(store.getState().error, null);
  assert.equal(store.getState().messages.length, 1);
  assert.equal(store.getState().messages[0].content, "Stop this question");
});


test("a response for a background conversation never enters active messages", async () => {
  const request = deferred();
  const store = loadStore(
    createApi({ sendMessage: async () => request.promise }),
  );
  store.setState({
    conversations: [conversation("one"), conversation("two")],
    activeConversationId: "one",
  });

  const sending = store.getState().send("Question");
  store.setState({
    activeConversationId: "two",
    messages: [message("two-existing", "user", "Existing", 0)],
  });
  request.resolve({
    user_message: message("one-user", "user", "Question", 0),
    assistant_message: message("one-assistant", "assistant", "Answer", 1),
    response: { answer: "Answer" },
  });
  await sending;

  assert.deepEqual(store.getState().messages.map((item) => item.id), [
    "two-existing",
  ]);
  assert.equal(store.getState().conversations[0].id, "one");
  assert.equal(store.getState().isSending, false);
});

test("reset invalidates pending requests and restores every state field", async () => {
  const request = deferred();
  const store = loadStore(
    createApi({ listConversations: async () => request.promise }),
  );

  const loading = store.getState().loadConversations();
  store.getState().reset();
  request.resolve({
    conversations: [conversation("stale")],
    next_cursor: "stale-cursor",
  });
  await loading;

  assert.deepEqual(store.getState().conversations, []);
  assert.equal(store.getState().activeConversationId, null);
  assert.equal(store.getState().isListLoading, false);
  assert.equal(store.getState().error, null);
});

test("rename normalizes titles and active delete clears message state", async () => {
  const renameCalls = [];
  const deleteCalls = [];
  const store = loadStore(
    createApi({
      renameConversation: async (...args) => renameCalls.push(args),
      deleteConversation: async (...args) => deleteCalls.push(args),
    }),
  );
  store.setState({
    conversations: [conversation("active")],
    activeConversationId: "active",
    messages: [message("message-1", "user", "Question", 0)],
    messageCursor: "cursor",
    hasMoreMessages: true,
  });

  await store.getState().rename("active", "  Updated   title  ");
  assert.equal(store.getState().conversations[0].title, "Updated title");
  assert.deepEqual(renameCalls, [["active", "Updated title"]]);

  await store.getState().remove("active");
  assert.deepEqual(deleteCalls, [["active"]]);
  assert.equal(store.getState().activeConversationId, null);
  assert.deepEqual(store.getState().messages, []);
  assert.equal(store.getState().messageCursor, null);
  assert.equal(store.getState().hasMoreMessages, false);
});
