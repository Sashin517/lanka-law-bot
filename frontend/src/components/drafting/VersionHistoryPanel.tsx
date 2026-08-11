"use client";

import { AlertTriangle, History } from "lucide-react";
import { useState } from "react";

import { VersionCard } from "@/components/drafting/VersionCard";
import type { IEditorService } from "@/lib/drafting/editorService";
import { useVersionStore } from "@/store/versionStore";
import type { DocumentVersion } from "@/types/drafting";

export interface VersionHistoryPanelProps {
  draftId: string | null;
  editor: IEditorService | null;
  onBeforeRestore?: () => void;
  onVersionRestored: (version: DocumentVersion) => void;
}

export function VersionHistoryPanel({
  draftId,
  editor,
  onBeforeRestore,
  onVersionRestored,
}: VersionHistoryPanelProps) {
  const {
    activeDraftId,
    versions,
    currentVersionId,
    restoreVersion,
  } = useVersionStore();
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const visibleVersions = activeDraftId === draftId ? versions : [];
  const visibleCurrentVersionId =
    activeDraftId === draftId ? currentVersionId : null;

  const handleRestore = (versionId: string) => {
    if (!editor || restoringId) return;
    setRestoringId(versionId);
    setError(null);
    try {
      onBeforeRestore?.();
      const restored = restoreVersion(versionId, editor);
      if (restored) onVersionRestored(restored);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The selected version could not be restored.",
      );
    } finally {
      setRestoringId(null);
    }
  };

  return (
    <section
      className="flex min-h-0 w-full flex-1 flex-col overflow-hidden"
      id="draft-version-sidebar"
      aria-label="Document version history"
    >
      <div className="flex items-center gap-2 px-4 py-3">
        <History size={13} className="text-[#D4AF37]" />
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Version History
        </p>
      </div>

      {error && (
        <p className="mx-3 mb-2 flex items-start gap-1.5 rounded-md bg-red-500/10 p-2 text-[10px] text-red-400" role="alert">
          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
          {error}
        </p>
      )}

      <div className="flex-1 space-y-2 overflow-y-auto px-3 pb-4 chat-scroll">
        {visibleVersions.length === 0 ? (
          <p className="rounded-lg border border-dashed border-slate-700 p-3 text-center text-[10px] text-slate-500">
            Version history begins when the draft is generated.
          </p>
        ) : (
          [...visibleVersions]
            .reverse()
            .map((version) => (
              <VersionCard
                key={version.id}
                version={version}
                selected={version.id === visibleCurrentVersionId}
                disabled={!editor || restoringId !== null}
                onRestore={handleRestore}
              />
            ))
        )}
      </div>
    </section>
  );
}
