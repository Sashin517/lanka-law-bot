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
import { DocumentBuilder } from "@/lib/drafting/documentBuilder";
import {
  connectSSE,
  isSSEEndpointUnavailableError,
} from "@/lib/sseClient";
import { useActivityStreamStore } from "@/store/activityStreamStore";
import type { TiptapDocument } from "@/types/drafting";

// ─── Store Interface ────────────────────────────────────────────

interface DraftDocumentState {
  // ── Document metadata ──
  draftId: string | null;
  title: string;
  originalPrompt: string;
  documentType: string;
  documentIds: string[];

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
  documentIds: [],
  documentJson: null,
  markdownContent: "",
  sources: [],
  isLoading: false,
  isEditing: false,
  error: null,
};

let activeDraftController: AbortController | null = null;
let draftRequestGeneration = 0;

// ─── Store Implementation ───────────────────────────────────────

function draftTitle(markdown: string, prompt: string): string {
  const firstHeading = markdown.match(/^#{1,6}\s+(.+)$/m)?.[1]?.trim();
  if (firstHeading) return firstHeading;

  const normalizedPrompt = prompt.replace(/\s+/g, " ").trim();
  return normalizedPrompt.length > 80
    ? `${normalizedPrompt.slice(0, 77)}…`
    : normalizedPrompt || "Untitled Draft";
}

export const useDraftDocumentStore = create<DraftDocumentStore>((set) => ({
  ...initialState,

  startDraft: async (question, documentIds) => {
    activeDraftController?.abort();
    const requestGeneration = ++draftRequestGeneration;
    const controller = new AbortController();
    activeDraftController = controller;

    set({
      isLoading: true,
      error: null,
      originalPrompt: question,
      markdownContent: "",
      documentJson: null,
      sources: [],
      title: "",
      documentType: "",
      documentIds: [...documentIds],
      draftId: crypto.randomUUID(),
    });

    const activityStore = useActivityStreamStore.getState();
    activityStore.startStream(createRequestId("draft-stream"));

    try {
      const payload = {
        question,
        mode: "drafting" as const,
        document_ids: documentIds.length > 0 ? documentIds : undefined,
      };
      let response: LegalQueryResponse;

      try {
        let streamedResponse: Record<string, unknown> | null = null;
        await connectSSE({
          endpoint: "/api/search/stream",
          payload,
          signal: controller.signal,
          onEvent: activityStore.processEvent,
          onComplete: (result) => {
            streamedResponse = result;
          },
        });
        if (controller.signal.aborted) throw abortError();
        if (!streamedResponse) {
          throw new Error("Draft stream completed without a final response");
        }
        response = streamedResponse as LegalQueryResponse;
      } catch (error) {
        if (!isSSEEndpointUnavailableError(error)) throw error;
        activityStore.reset();
        response = await sendLegalQuery(payload, { signal: controller.signal });
      }

      if (requestGeneration !== draftRequestGeneration) return;

      const markdownContent =
        response.markdown_content ?? response.answer ?? "";
      const documentJson = new DocumentBuilder().fromMarkdown(
        markdownContent,
        response.sources ?? [],
      );

      set({
        title: draftTitle(markdownContent, question),
        markdownContent,
        documentJson,
        sources: response.sources ?? [],
        isLoading: false,
      });
    } catch (err) {
      if (requestGeneration !== draftRequestGeneration) return;
      if (isAbortError(err)) {
        set({ isLoading: false });
        activityStore.endStream();
        return;
      }
      const message =
        err instanceof Error ? err.message : "Failed to generate draft";
      activityStore.setError(message);
      set({ isLoading: false, error: message });
    } finally {
      if (requestGeneration === draftRequestGeneration) {
        activityStore.endStream();
      }
      if (activeDraftController === controller) {
        activeDraftController = null;
      }
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
    activeDraftController?.abort();
    activeDraftController = null;
    draftRequestGeneration += 1;
    useActivityStreamStore.getState().reset();
    set({ ...initialState });
  },
}));

function createRequestId(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function abortError(): Error {
  if (typeof DOMException !== "undefined") {
    return new DOMException("The operation was aborted", "AbortError");
  }
  const error = new Error("The operation was aborted");
  error.name = "AbortError";
  return error;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}
