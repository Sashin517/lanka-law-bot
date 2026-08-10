/**
 * Draft Document Store — Document content, metadata, and loading state.
 *
 * Single Responsibility: Manages the lifecycle of a single draft document
 * from initial generation through content updates. Does NOT handle
 * versioning (→ versionStore) or chat editing (→ chatEditStore).
 *
 * @module store/draftDocumentStore
 */

import { create } from "zustand";

import type { SourceRef, LegalQueryResponse } from "@/lib/api";
import { sendLegalQuery } from "@/lib/api";
import type { TiptapDocument } from "@/types/drafting";

// ─── Store Interface ────────────────────────────────────────────

interface DraftDocumentState {
  // ── Document metadata ──
  draftId: string | null;
  title: string;
  originalPrompt: string;
  documentType: string;

  // ── Content ──
  documentJson: TiptapDocument | null;
  markdownContent: string;
  sources: SourceRef[];

  // ── Loading / error state ──
  isLoading: boolean;
  isEditing: boolean;
  error: string | null;
}

interface DraftDocumentActions {
  /**
   * Generate a new draft via the backend LangGraph pipeline.
   * Sets mode="drafting" and sends through /api/search.
   */
  startDraft: (question: string, documentIds: string[]) => Promise<void>;

  /**
   * Update document content from Tiptap editor onUpdate callback.
   * Called on every editor change (debounced by the editor component).
   */
  updateContent: (json: TiptapDocument, markdown: string) => void;

  /** Replace the document's source references. */
  setSources: (sources: SourceRef[]) => void;

  /** Set the document title (e.g. after AI generates it). */
  setTitle: (title: string) => void;

  /** Set loading state (for external consumers like chat edit). */
  setEditing: (isEditing: boolean) => void;

  /**
   * Load an existing draft from a version snapshot.
   * Used when restoring a previous version from the version store.
   */
  loadFromSnapshot: (
    json: TiptapDocument,
    markdown: string,
    sources: SourceRef[],
  ) => void;

  /** Reset all state to initial values. */
  reset: () => void;
}

export type DraftDocumentStore = DraftDocumentState & DraftDocumentActions;

// ─── Initial State ──────────────────────────────────────────────

const initialState: DraftDocumentState = {
  draftId: null,
  title: "",
  originalPrompt: "",
  documentType: "",
  documentJson: null,
  markdownContent: "",
  sources: [],
  isLoading: false,
  isEditing: false,
  error: null,
};

// ─── Store Implementation ───────────────────────────────────────

export const useDraftDocumentStore = create<DraftDocumentStore>((set, get) => ({
  ...initialState,

  startDraft: async (question, documentIds) => {
    set({
      isLoading: true,
      error: null,
      originalPrompt: question,
      markdownContent: "",
      documentJson: null,
      sources: [],
      title: "",
      documentType: "",
    });

    try {
      const response: LegalQueryResponse = await sendLegalQuery({
        question,
        mode: "drafting",
        document_ids: documentIds.length > 0 ? documentIds : undefined,
      });

      // Generate a stable draft ID for this session
      const draftId = crypto.randomUUID();

      set({
        draftId,
        markdownContent: response.markdown_content ?? response.answer ?? "",
        sources: response.sources ?? [],
        isLoading: false,
        // Title and documentType will be set by the page component
        // once it parses the response or the formatter node provides them
      });
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to generate draft";
      set({ isLoading: false, error: message });
    }
  },

  updateContent: (json, markdown) => {
    set({ documentJson: json, markdownContent: markdown });
  },

  setSources: (sources) => {
    set({ sources });
  },

  setTitle: (title) => {
    set({ title });
  },

  setEditing: (isEditing) => {
    set({ isEditing });
  },

  loadFromSnapshot: (json, markdown, sources) => {
    set({
      documentJson: json,
      markdownContent: markdown,
      sources,
      isEditing: false,
      error: null,
    });
  },

  reset: () => {
    set(initialState);
  },
}));
