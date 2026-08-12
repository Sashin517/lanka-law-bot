/** Persistent research-conversation state backed by the API Facade. */

import { create } from "zustand";

import {
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  renameConversation,
  sendMessage,
} from "@/lib/conversationApi";
import type {
  ConversationMessage,
  ConversationSummary,
  MessageAttachment,
} from "@/types/conversation";
import type { QueryMode } from "@/types/QueryMode";

interface ConversationState {
  conversations: ConversationSummary[];
  activeConversationId: string | null;
  messages: ConversationMessage[];
  listCursor: string | null;
  messageCursor: string | null;
  isListLoading: boolean;
  isMessagesLoading: boolean;
  isCreating: boolean;
  isSending: boolean;
  hasMoreConversations: boolean;
  hasMoreMessages: boolean;
  error: string | null;
}

interface ConversationActions {
  loadConversations: () => Promise<void>;
  loadMoreConversations: () => Promise<void>;
  newConversation: (queryMode?: QueryMode) => Promise<string>;
  selectConversation: (conversationId: string) => Promise<void>;
  loadMoreMessages: () => Promise<void>;
  rename: (conversationId: string, title: string) => Promise<void>;
  remove: (conversationId: string) => Promise<void>;
  send: (
    content: string,
    queryMode?: QueryMode,
    documentIds?: string[],
    attachments?: MessageAttachment[],
  ) => Promise<void>;
  stopSending: () => void;
  clearError: () => void;
  clearActive: () => void;
  reset: () => void;
}

export type ConversationStore = ConversationState & ConversationActions;

const initialState: ConversationState = {
  conversations: [],
  activeConversationId: null,
  messages: [],
  listCursor: null,
  messageCursor: null,
  isListLoading: false,
  isMessagesLoading: false,
  isCreating: false,
  isSending: false,
  hasMoreConversations: true,
  hasMoreMessages: false,
  error: null,
};

let lifecycleGeneration = 0;
let listRequestGeneration = 0;
let messageRequestGeneration = 0;
let activeSendController: AbortController | null = null;

export const useConversationStore = create<ConversationStore>((set, get) => ({
  ...initialState,

  loadConversations: async () => {
    const requestGeneration = ++listRequestGeneration;
    const lifecycle = lifecycleGeneration;
    set({ isListLoading: true, error: null });
    try {
      const response = await listConversations(null, 30);
      if (!isCurrent(lifecycle, requestGeneration, listRequestGeneration)) return;
      set({
        conversations: uniqueById(response.conversations),
        listCursor: response.next_cursor,
        hasMoreConversations: response.next_cursor !== null,
        isListLoading: false,
      });
    } catch (error) {
      if (!isCurrent(lifecycle, requestGeneration, listRequestGeneration)) return;
      set({ isListLoading: false, error: errorMessage(error, "Failed to load conversations") });
    }
  },

  loadMoreConversations: async () => {
    const state = get();
    if (!state.hasMoreConversations || state.isListLoading || !state.listCursor) return;

    const requestGeneration = ++listRequestGeneration;
    const lifecycle = lifecycleGeneration;
    set({ isListLoading: true, error: null });
    try {
      const response = await listConversations(state.listCursor, 30);
      if (!isCurrent(lifecycle, requestGeneration, listRequestGeneration)) return;
      set((current) => ({
        conversations: mergeById(current.conversations, response.conversations),
        listCursor: response.next_cursor,
        hasMoreConversations: response.next_cursor !== null,
        isListLoading: false,
      }));
    } catch (error) {
      if (!isCurrent(lifecycle, requestGeneration, listRequestGeneration)) return;
      set({ isListLoading: false, error: errorMessage(error, "Failed to load more conversations") });
    }
  },

  newConversation: async (queryMode = "quick_qa") => {
    if (get().isCreating) {
      throw new Error("A conversation is already being created");
    }
    const lifecycle = lifecycleGeneration;
    ++listRequestGeneration;
    set({ isCreating: true, isListLoading: false, error: null });
    try {
      const conversation = await createConversation("New Chat", queryMode);
      if (lifecycle === lifecycleGeneration) {
        ++messageRequestGeneration;
        set((state) => ({
          conversations: [
            conversation,
            ...state.conversations.filter((item) => item.id !== conversation.id),
          ],
          activeConversationId: conversation.id,
          messages: [],
          messageCursor: null,
          hasMoreMessages: false,
          isCreating: false,
          isMessagesLoading: false,
        }));
      }
      return conversation.id;
    } catch (error) {
      if (lifecycle === lifecycleGeneration) {
        set({ isCreating: false, error: errorMessage(error, "Failed to create conversation") });
      }
      throw error;
    }
  },

  selectConversation: async (conversationId) => {
    const requestGeneration = ++messageRequestGeneration;
    const lifecycle = lifecycleGeneration;
    set({
      activeConversationId: conversationId,
      messages: [],
      messageCursor: null,
      hasMoreMessages: false,
      isMessagesLoading: true,
      error: null,
    });
    try {
      const response = await listMessages(conversationId, null, 50);
      if (!isCurrent(lifecycle, requestGeneration, messageRequestGeneration)) return;
      if (get().activeConversationId !== conversationId) return;
      set({
        messages: uniqueById(response.messages),
        messageCursor: response.next_cursor,
        hasMoreMessages: response.next_cursor !== null,
        isMessagesLoading: false,
      });
    } catch (error) {
      if (!isCurrent(lifecycle, requestGeneration, messageRequestGeneration)) return;
      if (get().activeConversationId !== conversationId) return;
      set({ isMessagesLoading: false, error: errorMessage(error, "Failed to load messages") });
    }
  },

  loadMoreMessages: async () => {
    const state = get();
    if (
      !state.activeConversationId ||
      !state.messageCursor ||
      !state.hasMoreMessages ||
      state.isMessagesLoading
    ) {
      return;
    }

    const conversationId = state.activeConversationId;
    const requestGeneration = ++messageRequestGeneration;
    const lifecycle = lifecycleGeneration;
    set({ isMessagesLoading: true, error: null });
    try {
      const response = await listMessages(conversationId, state.messageCursor, 50);
      if (!isCurrent(lifecycle, requestGeneration, messageRequestGeneration)) return;
      if (get().activeConversationId !== conversationId) return;
      set((current) => ({
        messages: mergeMessages(current.messages, response.messages),
        messageCursor: response.next_cursor,
        hasMoreMessages: response.next_cursor !== null,
        isMessagesLoading: false,
      }));
    } catch (error) {
      if (!isCurrent(lifecycle, requestGeneration, messageRequestGeneration)) return;
      if (get().activeConversationId !== conversationId) return;
      set({ isMessagesLoading: false, error: errorMessage(error, "Failed to load more messages") });
    }
  },

  rename: async (conversationId, title) => {
    let normalizedTitle: string;
    try {
      normalizedTitle = normalizeTitle(title);
    } catch (error) {
      set({ error: errorMessage(error, "Invalid conversation title") });
      throw error;
    }
    const lifecycle = lifecycleGeneration;
    set({ error: null });
    try {
      await renameConversation(conversationId, normalizedTitle);
      if (lifecycle !== lifecycleGeneration) return;
      ++listRequestGeneration;
      set((state) => ({
        isListLoading: false,
        conversations: state.conversations.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, title: normalizedTitle }
            : conversation,
        ),
      }));
    } catch (error) {
      if (lifecycle === lifecycleGeneration) {
        set({ error: errorMessage(error, "Failed to rename conversation") });
      }
      throw error;
    }
  },

  remove: async (conversationId) => {
    const lifecycle = lifecycleGeneration;
    set({ error: null });
    try {
      await deleteConversation(conversationId);
      if (lifecycle !== lifecycleGeneration) return;
      ++listRequestGeneration;
      ++messageRequestGeneration;
      set((state) => {
        const removedActive = state.activeConversationId === conversationId;
        return {
          conversations: state.conversations.filter((item) => item.id !== conversationId),
          activeConversationId: removedActive ? null : state.activeConversationId,
          messages: removedActive ? [] : state.messages,
          messageCursor: removedActive ? null : state.messageCursor,
          hasMoreMessages: removedActive ? false : state.hasMoreMessages,
          isListLoading: false,
          isMessagesLoading: false,
        };
      });
    } catch (error) {
      if (lifecycle === lifecycleGeneration) {
        set({ error: errorMessage(error, "Failed to delete conversation") });
      }
      throw error;
    }
  },

  send: async (
    content,
    queryMode = "quick_qa",
    documentIds = [],
    attachments = [],
  ) => {
    const state = get();
    if (!state.activeConversationId) {
      set({ error: "Select or create a conversation before sending a message" });
      return;
    }
    if (state.isSending) return;

    const normalizedContent = content.trim();
    if (!normalizedContent) {
      set({ error: "Message cannot be empty" });
      return;
    }

    const conversationId = state.activeConversationId;
    const lifecycle = lifecycleGeneration;
    const controller = new AbortController();
    activeSendController = controller;

    const tempId = `temp-user-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    const maxSeq =
      state.messages.length > 0
        ? Math.max(...state.messages.map((m) => m.sequence_number))
        : -1;
    const optimisticUserMessage: ConversationMessage = {
      id: tempId,
      role: "user",
      content: normalizedContent,
      markdown_content: null,
      confidence: null,
      disclaimer: null,
      sequence_number: maxSeq + 1,
      query_mode: queryMode,
      citations: [],
      attachments: attachments,
      created_at: new Date().toISOString(),
    };

    set((current) => ({
      isSending: true,
      error: null,
      messages:
        current.activeConversationId === conversationId
          ? [...current.messages, optimisticUserMessage]
          : current.messages,
    }));

    try {
      const response = await sendMessage(
        conversationId,
        normalizedContent,
        queryMode,
        documentIds,
        attachments,
        { signal: controller.signal },
      );
      if (lifecycle !== lifecycleGeneration) return;

      ++listRequestGeneration;
      set((current) => {
        const updated = current.conversations.find((item) => item.id === conversationId);
        const updatedConversation = updated
          ? {
              ...updated,
              title:
                updated.title === "New Chat"
                  ? buildAutoTitle(normalizedContent)
                  : updated.title,
              message_count: Math.max(
                updated.message_count + 2,
                response.assistant_message.sequence_number + 1,
              ),
              last_message_preview: response.assistant_message.content.slice(0, 200),
              updated_at: response.assistant_message.created_at,
            }
          : null;
        return {
          messages:
            current.activeConversationId === conversationId
              ? mergeMessages(
                  current.messages.filter((m) => m.id !== tempId),
                  [response.user_message, response.assistant_message],
                )
              : current.messages,
          conversations: updatedConversation
            ? [
                updatedConversation,
                ...current.conversations.filter((item) => item.id !== conversationId),
              ]
            : current.conversations,
          isListLoading: false,
          isSending: false,
        };
      });
    } catch (error) {
      if (lifecycle === lifecycleGeneration) {
        set((current) => ({
          isSending: false,
          error: isAbortError(error)
            ? null
            : errorMessage(error, "Failed to send message"),
          messages: isAbortError(error)
            ? current.messages
            : current.messages.filter((m) => m.id !== tempId),
        }));
      }
    } finally {
      if (activeSendController === controller) {
        activeSendController = null;
      }
    }
  },

  stopSending: () => {
    activeSendController?.abort();
  },

  clearError: () => set({ error: null }),

  clearActive: () => {
    ++messageRequestGeneration;
    set({
      activeConversationId: null,
      messages: [],
      messageCursor: null,
      hasMoreMessages: false,
      isMessagesLoading: false,
    });
  },

  reset: () => {
    activeSendController?.abort();
    activeSendController = null;
    ++lifecycleGeneration;
    ++listRequestGeneration;
    ++messageRequestGeneration;
    set({ ...initialState });
  },
}));

function isCurrent(
  lifecycle: number,
  requestGeneration: number,
  currentRequestGeneration: number,
): boolean {
  return lifecycle === lifecycleGeneration && requestGeneration === currentRequestGeneration;
}

function normalizeTitle(title: string): string {
  const normalized = title.replace(/\s+/g, " ").trim();
  if (!normalized) throw new TypeError("Conversation title cannot be empty");
  if (normalized.length > 512) throw new RangeError("Conversation title cannot exceed 512 characters");
  return normalized;
}

function buildAutoTitle(firstMessage: string): string {
  const normalized = firstMessage.replace(/\s+/g, " ").trim();
  return normalized.length <= 60
    ? normalized
    : `${normalized.slice(0, 60).trimEnd()}…`;
}

function uniqueById<T extends { id: string }>(items: T[]): T[] {
  return mergeById([], items);
}

function mergeById<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  const result = [...existing];
  const indexes = new Map(result.map((item, index) => [item.id, index]));
  for (const item of incoming) {
    const index = indexes.get(item.id);
    if (index === undefined) {
      indexes.set(item.id, result.length);
      result.push(item);
    } else {
      result[index] = item;
    }
  }
  return result;
}

function mergeMessages(
  existing: ConversationMessage[],
  incoming: ConversationMessage[],
): ConversationMessage[] {
  return mergeById(existing, incoming).sort(
    (left, right) =>
      left.sequence_number - right.sequence_number ||
      left.id.localeCompare(right.id),
  );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

function isAbortError(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error.name === "AbortError" || error.name === "TimeoutError")
  );
}
