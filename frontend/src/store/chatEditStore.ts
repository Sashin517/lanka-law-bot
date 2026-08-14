/**
 * Chat Edit Store — Chat-driven editing state for the drafting panel.
 *
 * Single Responsibility: Manages the chat message list, text selection
 * context, chat mode (ask vs edit), and the async lifecycle of sending
 * edit requests to the backend. Does NOT apply edits to the editor
 * (→ ChatEditService mediator) or track versions (→ versionStore).
 *
 * @module store/chatEditStore
 */

import { create } from "zustand";

import type {
  DraftChatMessage,
  EditorSelection,
  EditOperation,
  ChatMode,
  ChatMessageStatus,
  PendingEditSuggestion,
} from "@/types/drafting";
import type { SourceRef } from "@/lib/api";

export type { DraftEditPayload, DraftEditResult } from "@/lib/api";

// ─── Store Interface ────────────────────────────────────────────

interface ChatEditState {
  /** Ordered list of chat messages in this drafting session. */
  messages: DraftChatMessage[];
  /** Currently selected text in the Tiptap editor (if any). */
  currentSelection: EditorSelection | null;
  /** One-shot intent to focus the chat composer after an explicit selection action. */
  composerFocusRequested: boolean;
  /** Whether the backend is processing an edit request. */
  isProcessing: boolean;
  /** Current chat panel mode: "ask" for questions, "edit" for edits. */
  chatMode: ChatMode;
  /** Error message from the last failed operation. */
  error: string | null;
}

interface ChatEditActions {
  /** Set the current text selection from the Tiptap editor. */
  setSelection: (selection: EditorSelection | null) => void;

  /** Request composer focus after the user sends a selection to Ask/Edit. */
  requestComposerFocus: () => void;

  /** Clear the one-shot composer focus request after the panel handles it. */
  consumeComposerFocusRequest: () => void;

  /** Switch between "ask" and "edit" chat modes. */
  setChatMode: (mode: ChatMode) => void;

  /**
   * Add a user message to the chat history.
   * Returns the message ID for tracking.
   */
  addUserMessage: (content: string, selection?: EditorSelection) => string;

  /**
   * Add an assistant (AI) response to the chat history.
   * Includes the edit operation details for later application.
   */
  addAssistantMessage: (
    content: string,
    options?: {
      editOperation?: EditOperation;
      editPath?: "light" | "heavy";
      status?: ChatMessageStatus;
      sources?: SourceRef[];
      suggestion?: PendingEditSuggestion;
    },
  ) => string;

  /**
   * Mark a specific assistant message's edit as applied.
   * Called by the ChatEditService after successfully applying to the editor.
   */
  markEditApplied: (messageId: string) => void;

  /** Resolve a pending suggestion without mutating document content. */
  setMessageStatus: (messageId: string, status: ChatMessageStatus) => void;

  /** Set processing state (for loading indicators). */
  setProcessing: (isProcessing: boolean) => void;

  /** Set error state. */
  setError: (error: string | null) => void;

  /** Clear all chat messages (e.g. when starting a new draft). */
  clearMessages: () => void;

  /** Reset all state to initial values. */
  reset: () => void;
}

export type ChatEditStore = ChatEditState & ChatEditActions;

// ─── Initial State ──────────────────────────────────────────────

const initialState: ChatEditState = {
  messages: [],
  currentSelection: null,
  composerFocusRequested: false,
  isProcessing: false,
  chatMode: "edit",
  error: null,
};

// ─── Store Implementation ───────────────────────────────────────

export const useChatEditStore = create<ChatEditStore>((set) => ({
  ...initialState,

  setSelection: (selection) => {
    set({ currentSelection: selection });
  },

  requestComposerFocus: () => {
    set({ composerFocusRequested: true });
  },

  consumeComposerFocusRequest: () => {
    set({ composerFocusRequested: false });
  },

  setChatMode: (mode) => {
    set({ chatMode: mode });
  },

  addUserMessage: (content, selection) => {
    const messageId = crypto.randomUUID();

    const message: DraftChatMessage = {
      id: messageId,
      role: "user",
      content,
      timestamp: new Date().toISOString(),
      selection,
      appliedToEditor: false,
    };

    set((state) => ({
      messages: [...state.messages, message],
      error: null,
    }));

    return messageId;
  },

  addAssistantMessage: (content, options = {}) => {
    const messageId = crypto.randomUUID();

    const message: DraftChatMessage = {
      id: messageId,
      role: "assistant",
      content,
      timestamp: new Date().toISOString(),
      appliedToEditor: false,
      editOperation: options.editOperation,
      editPath: options.editPath,
      status: options.status ?? "informational",
      sources: options.sources,
      suggestion: options.suggestion,
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return messageId;
  },

  markEditApplied: (messageId) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId
          ? { ...msg, appliedToEditor: true, status: "applied" }
          : msg,
      ),
    }));
  },

  setMessageStatus: (messageId, status) => {
    set((state) => ({
      messages: state.messages.map((message) =>
        message.id === messageId ? { ...message, status } : message,
      ),
    }));
  },

  setProcessing: (isProcessing) => {
    set({ isProcessing });
  },

  setError: (error) => {
    set({ error, isProcessing: false });
  },

  clearMessages: () => {
    set({ messages: [] });
  },

  reset: () => {
    set(initialState);
  },
}));
