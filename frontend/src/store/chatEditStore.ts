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

import type { SourceRef, ExecutionTrace } from "@/lib/api";
import type {
  DraftChatMessage,
  EditorSelection,
  EditOperation,
  ChatMode,
} from "@/types/drafting";

// ─── API Types (matching the plan's DraftEditPayload / Result) ──

export interface DraftEditPayload {
  draft_id: string;
  instruction: string;
  selected_text: string | null;
  selection_start: number | null;
  selection_end: number | null;
  current_content: string;
  document_ids: string[];
}

export interface DraftEditResult {
  edit_type: string;
  original_text: string;
  edited_text: string;
  markdown_content: string;
  sources: SourceRef[];
  edit_summary: string;
  confidence: string;
  edit_path: "light" | "heavy";
  execution_trace?: ExecutionTrace | null;
}

// ─── Store Interface ────────────────────────────────────────────

interface ChatEditState {
  /** Ordered list of chat messages in this drafting session. */
  messages: DraftChatMessage[];
  /** Currently selected text in the Tiptap editor (if any). */
  currentSelection: EditorSelection | null;
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
    editOperation?: EditOperation,
    editPath?: "light" | "heavy",
  ) => string;

  /**
   * Mark a specific assistant message's edit as applied.
   * Called by the ChatEditService after successfully applying to the editor.
   */
  markEditApplied: (messageId: string) => void;

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
  isProcessing: false,
  chatMode: "edit",
  error: null,
};

// ─── Store Implementation ───────────────────────────────────────

export const useChatEditStore = create<ChatEditStore>((set, get) => ({
  ...initialState,

  setSelection: (selection) => {
    set({ currentSelection: selection });
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

  addAssistantMessage: (content, editOperation, editPath) => {
    const messageId = crypto.randomUUID();

    const message: DraftChatMessage = {
      id: messageId,
      role: "assistant",
      content,
      timestamp: new Date().toISOString(),
      appliedToEditor: false,
      editOperation,
      editPath,
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return messageId;
  },

  markEditApplied: (messageId) => {
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId ? { ...msg, appliedToEditor: true } : msg,
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
