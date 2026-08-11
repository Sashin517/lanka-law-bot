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
          ? "border-[#D4AF37]/40 bg-[#D4AF37]/10"
          : "border-slate-700/50 bg-[#1D2530]/60 hover:border-slate-600"
      }`}
      aria-current={selected ? "true" : undefined}
    >
      <div className="mb-1.5 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {version.createdBy === "ai" ? (
            <Bot size={13} className="shrink-0 text-[#D4AF37]" />
          ) : (
            <UserRound size={13} className="shrink-0 text-sky-400" />
          )}
          <span className="truncate text-xs font-medium text-white">
            {version.label}
          </span>
        </div>
        {selected && (
          <span className="rounded bg-[#D4AF37]/20 px-1.5 py-0.5 text-[9px] font-medium text-[#D4AF37]">
            Selected
          </span>
        )}
      </div>

      <p className="line-clamp-3 text-[10px] leading-relaxed text-slate-400">
        {version.editSummary}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2">
        <time
          dateTime={version.createdAt}
          className="text-[9px] text-slate-600"
        >
          {formatVersionTime(version.createdAt)}
        </time>
        {!selected && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onRestore(version.id)}
            className="flex items-center gap-1 rounded px-1.5 py-1 text-[9px] font-medium text-slate-400 transition hover:bg-slate-700 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
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
