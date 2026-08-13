"use client";

import type { SourceRef } from "@/lib/api";
import type { IEditorService } from "@/lib/drafting/editorService";
import type { DocumentVersion, TiptapDocument } from "@/types/drafting";
import { SourceVerificationPanel } from "./SourceVerificationPanel";
import { VersionHistoryPanel } from "./VersionHistoryPanel";

export type DraftSidebarView = "versions" | "sources";

export interface DraftSidebarProps {
  activeView: DraftSidebarView;
  draftId: string | null;
  originalPrompt: string;
  editor: IEditorService | null;
  document: TiptapDocument | null;
  sources: SourceRef[];
  activeCitationId?: string | null;
  onBeforeRestore?: () => void;
  onVersionRestored: (version: DocumentVersion) => void;
}

export function DraftSidebar({
  activeView,
  draftId,
  originalPrompt,
  editor,
  document,
  sources,
  activeCitationId = null,
  onBeforeRestore,
  onVersionRestored,
}: DraftSidebarProps) {
  return (
    <aside
      className="flex w-[300px] shrink-0 flex-col overflow-hidden border-r border-app-border/50 bg-app-panel"
      id="draft-left-sidebar"
      aria-label="Draft navigation"
    >
      <div className="border-b border-app-border/50 p-4">
        <p className="mb-1.5 text-[10px] uppercase tracking-wider text-app-subtle">
          Prompt
        </p>
        <p className="line-clamp-4 text-xs leading-relaxed text-app-tertiary">
          {originalPrompt || "No prompt provided"}
        </p>
      </div>

      <div className="border-b border-app-border/50 px-4 py-2">
        <p className="flex items-center gap-1 text-[10px] text-app-subtle">
          <span className="inline-block h-2 w-2 rounded-full bg-app-success" />
          Saved locally
        </p>
      </div>

      {activeView === "versions" ? (
        <div
          id="draft-sidebar-versions-panel"
          role="region"
          aria-label="Document versions"
          className="flex min-h-0 flex-1"
        >
          <VersionHistoryPanel
            draftId={draftId}
            editor={editor}
            onBeforeRestore={onBeforeRestore}
            onVersionRestored={onVersionRestored}
          />
        </div>
      ) : (
        <div
          id="draft-sidebar-sources-panel"
          role="region"
          aria-label="Source verification"
          className="flex min-h-0 flex-1"
        >
          <SourceVerificationPanel
            document={document}
            sources={sources}
            activeCitationId={activeCitationId}
          />
        </div>
      )}
    </aside>
  );
}
