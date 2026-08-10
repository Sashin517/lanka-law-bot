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
import type { DocumentVersion, TiptapDocument } from "@/types/drafting";

// ─── Store Interface ────────────────────────────────────────────

interface VersionState {
  /** Ordered list of document versions (oldest first). */
  versions: DocumentVersion[];
  /** ID of the currently active version. */
  currentVersionId: string | null;
  /** Whether "Show Edits" diff highlighting mode is active. */
  showEditsMode: boolean;
}

interface VersionActions {
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
  ) => DocumentVersion;

  /** Add a pre-built version object (e.g. from backend persistence). */
  addVersion: (version: DocumentVersion) => void;

  /** Set the active version by ID (for version restore). */
  setCurrentVersion: (id: string) => void;

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
  versions: [],
  currentVersionId: null,
  showEditsMode: false,
};

// ─── Store Implementation ───────────────────────────────────────

export const useVersionStore = create<VersionStore>()(
  persist(
    (set, get) => ({
      ...initialState,

      createVersion: (content, sources, editSummary, createdBy) => {
        const state = get();
        const versionNumber = state.versions.length + 1;
        const parentVersionId = state.currentVersionId;

        const newVersion: DocumentVersion = {
          id: crypto.randomUUID(),
          versionNumber,
          label: `Version ${versionNumber}`,
          content,
          sources: [...sources],
          createdAt: new Date().toISOString(),
          createdBy,
          editSummary,
          parentVersionId,
        };

        set({
          versions: [...state.versions, newVersion],
          currentVersionId: newVersion.id,
        });

        return newVersion;
      },

      addVersion: (version) => {
        set((state) => ({
          versions: [...state.versions, version],
          currentVersionId: version.id,
        }));
      },

      setCurrentVersion: (id) => {
        const version = get().versions.find((v) => v.id === id);
        if (version) {
          set({ currentVersionId: id });
        }
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
        set(initialState);
      },
    }),
    {
      name: "lanka-law-bot-draft-versions",
      storage: createJSONStorage(() => localStorage),
      /**
       * Only persist version metadata and content, not derived state.
       * `showEditsMode` resets to false on page reload.
       */
      partialize: (state) => ({
        versions: state.versions,
        currentVersionId: state.currentVersionId,
      }),
    },
  ),
);
