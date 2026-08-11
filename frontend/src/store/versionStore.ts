/**
 * Version Store — Document version history and snapshot management.
 *
 * Single Responsibility: Manages the ordered chain of document versions
 * (Memento pattern). Each version is a full JSON snapshot of the Tiptap
 * document, forming a singly-linked list via `parentVersionId`.
 *
 * Storage: Zustand with `persist` middleware using `localStorage` for MVP.
 * Production: Extend to backend persistence via `/api/draft/versions`.
 *
 * @module store/versionStore
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { SourceRef } from "@/lib/api";
import type { IEditorService } from "@/lib/drafting/editorService";
import {
  validateVersionChain,
  versionControlService,
} from "@/lib/drafting/versionControlService";
import type { DocumentVersion, TiptapDocument } from "@/types/drafting";

// ─── Store Interface ────────────────────────────────────────────

interface VersionState {
  /** Draft owning this isolated version chain. */
  activeDraftId: string | null;
  /** Ordered list of document versions (oldest first). */
  versions: DocumentVersion[];
  /** ID of the currently active version. */
  currentVersionId: string | null;
  /** Whether "Show Edits" diff highlighting mode is active. */
  showEditsMode: boolean;
}

interface VersionActions {
  /** Start or resume an isolated version chain for one draft. */
  initializeDraft: (draftId: string) => void;

  /**
   * Create a new version snapshot from the current editor state.
   *
   * Automatically increments `versionNumber` and links to the
   * current version via `parentVersionId`.
   */
  createVersion: (
    content: TiptapDocument,
    sources: SourceRef[],
    editSummary: string,
    createdBy: "ai" | "user",
  ) => DocumentVersion | null;

  /** Add a pre-built version object (e.g. from backend persistence). */
  addVersion: (version: DocumentVersion) => void;

  /** Restore an historic snapshot by appending a new latest version. */
  restoreVersion: (
    id: string,
    editor: IEditorService,
  ) => DocumentVersion | null;

  /** Toggle "Show Edits" diff highlighting mode. */
  toggleShowEdits: () => void;

  /** Set "Show Edits" mode explicitly. */
  setShowEditsMode: (enabled: boolean) => void;

  /** Get the original (first) version in the chain. */
  getOriginalVersion: () => DocumentVersion | undefined;

  /** Get the currently active version object. */
  getCurrentVersion: () => DocumentVersion | undefined;

  /** Get a specific version by ID. */
  getVersion: (id: string) => DocumentVersion | undefined;

  /** Get the version count. */
  getVersionCount: () => number;

  /** Clear all version history (e.g. when starting a new draft). */
  reset: () => void;
}

export type VersionStore = VersionState & VersionActions;

// ─── Initial State ──────────────────────────────────────────────

const initialState: VersionState = {
  activeDraftId: null,
  versions: [],
  currentVersionId: null,
  showEditsMode: false,
};

function mergePersistedVersionState(
  persistedState: unknown,
  currentState: VersionStore,
): VersionStore {
  if (!persistedState || typeof persistedState !== "object") {
    return currentState;
  }

  const persisted = persistedState as Partial<VersionState>;
  if (!Array.isArray(persisted.versions)) return currentState;

  try {
    validateVersionChain(persisted.versions);
    const currentVersionId = persisted.currentVersionId ?? null;
    if (
      currentVersionId &&
      !persisted.versions.some((version) => version.id === currentVersionId)
    ) {
      return currentState;
    }

    return {
      ...currentState,
      activeDraftId:
        typeof persisted.activeDraftId === "string"
          ? persisted.activeDraftId
          : null,
      versions: persisted.versions,
      currentVersionId,
      showEditsMode: false,
    };
  } catch {
    // Treat malformed or partially written localStorage data as unavailable.
    return currentState;
  }
}

// ─── Store Implementation ───────────────────────────────────────

export const useVersionStore = create<VersionStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      initializeDraft: (draftId) => {
        const state = get();
        if (state.activeDraftId === draftId) return;
        versionControlService.hydrate([], null);
        set({
          activeDraftId: draftId,
          versions: [],
          currentVersionId: null,
          showEditsMode: false,
        });
      },

      createVersion: (content, sources, editSummary, createdBy) => {
        const state = get();
        versionControlService.hydrate(
          state.versions,
          state.currentVersionId,
        );
        const newVersion = versionControlService.createSnapshot(
          content,
          sources,
          editSummary,
          createdBy,
        );
        if (!newVersion) return null;

        set({
          versions: versionControlService.getVersionHistory(),
          currentVersionId: versionControlService.getCurrentVersionId(),
        });

        return newVersion;
      },

      addVersion: (version) => {
        const state = get();
        versionControlService.hydrate(
          state.versions,
          state.currentVersionId,
        );
        versionControlService.appendSnapshot(version);
        set({
          versions: versionControlService.getVersionHistory(),
          currentVersionId: versionControlService.getCurrentVersionId(),
        });
      },

      restoreVersion: (id, editor) => {
        const state = get();
        versionControlService.hydrate(
          state.versions,
          state.currentVersionId,
        );
        const restored = versionControlService.restoreVersion(id, editor);
        if (!restored) return null;
        set({
          versions: versionControlService.getVersionHistory(),
          currentVersionId: versionControlService.getCurrentVersionId(),
          showEditsMode: false,
        });
        return restored.newVersion;
      },

      toggleShowEdits: () => {
        set((state) => ({ showEditsMode: !state.showEditsMode }));
      },

      setShowEditsMode: (enabled) => {
        set({ showEditsMode: enabled });
      },

      getOriginalVersion: () => {
        const { versions } = get();
        return versions.length > 0 ? versions[0] : undefined;
      },

      getCurrentVersion: () => {
        const { versions, currentVersionId } = get();
        if (!currentVersionId) return undefined;
        return versions.find((v) => v.id === currentVersionId);
      },

      getVersion: (id) => {
        return get().versions.find((v) => v.id === id);
      },

      getVersionCount: () => {
        return get().versions.length;
      },

      reset: () => {
        versionControlService.hydrate([], null);
        set(initialState);
      },
    }),
    {
      name: "lanka-law-bot-draft-versions",
      version: 1,
      storage: createJSONStorage(() => localStorage),
      merge: mergePersistedVersionState,
      /**
       * Only persist version metadata and content, not derived state.
       * `showEditsMode` resets to false on page reload.
       */
      partialize: (state) => ({
        versions: state.versions,
        currentVersionId: state.currentVersionId,
        activeDraftId: state.activeDraftId,
      }),
    },
  ),
);
