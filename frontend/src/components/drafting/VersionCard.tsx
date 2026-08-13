"use client";

import { Bot, RotateCcw, UserRound } from "lucide-react";

import type { DocumentVersion } from "@/types/drafting";

export interface VersionCardProps {
  version: DocumentVersion;
  selected: boolean;
  disabled?: boolean;
  onRestore: (versionId: string) => void;
}

export function VersionCard({
  version,
  selected,
  disabled = false,
  onRestore,
}: VersionCardProps) {
  return (
    <article
      className={`rounded-lg border p-3 transition ${
        selected
          ? "border-app-accent/40 bg-app-accent/10"
          : "border-app-border/50 bg-app-panel-muted/60 hover:border-app-border"
      }`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {version.createdBy === "ai" ? (
            <Bot size={13} className="shrink-0 text-app-accent" />
          ) : (
            <UserRound size={13} className="shrink-0 text-app-info" />
          )}
          <span className="truncate text-xs font-medium text-app-strong">
            {version.label}
          </span>
        </div>
        {selected && (
          <span className="rounded bg-app-accent/20 px-1.5 py-0.5 text-[9px] font-medium text-app-accent">
            Selected
          </span>
        )}
      </div>

      <p className="line-clamp-3 text-[10px] leading-relaxed text-app-muted">
        {version.editSummary}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <time
          dateTime={version.createdAt}
          className="text-[9px] text-app-faint"
        >
          {formatVersionTime(version.createdAt)}
        </time>
        {!selected && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRestore(version.id)}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-[9px] font-medium text-app-muted transition hover:bg-app-hover hover:text-app-strong disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={`Restore ${version.label}`}
          >
            <RotateCcw size={10} />
            Restore
          </button>
        )}
      </div>
    </article>
  );
}

function formatVersionTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
