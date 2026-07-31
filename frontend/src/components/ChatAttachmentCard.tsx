"use client";

import { AlertTriangle, Check, FileText, Loader2, X } from "lucide-react";

import type { UploadedDocument } from "@/types/documents";

interface ChatAttachmentCardProps {
  document: UploadedDocument;
  onRemove: (documentId: string) => void;
}

const statusLabel: Record<UploadedDocument["status"], string> = {
  queued: "Queued",
  processing: "Processing…",
  completed: "Ready",
  failed: "Failed",
};

function fileType(filename: string): string {
  return filename.split(".").pop()?.toUpperCase() ?? "FILE";
}

export function ChatAttachmentCard({ document, onRemove }: ChatAttachmentCardProps) {
  const isProcessing = document.status === "queued" || document.status === "processing";
  const isFailed = document.status === "failed";
  const isComplete = document.status === "completed";

  return (
    /* ── Design system tokens ──
       Normal: border-light-blue/20 bg-dark-blue (card surface)
       Failed: red semantic border
       Hover: border-light-blue/40 lift                               */
    <div
      title={isFailed && document.error ? document.error : document.filename}
      className={`
        flex w-full max-w-[390px] items-center gap-3 rounded-xl border px-3 py-2.5 transition-colors
        ${isFailed
          ? "border-red-500/30 bg-red-950/15"
          : "border-light-blue/20 bg-dark-blue hover:border-light-blue/35"
        }
      `}
    >
      {/* File type icon badge */}
      <div
        className={`
          flex h-10 w-10 shrink-0 items-center justify-center rounded-lg
          ${isFailed ? "bg-red-500/20 border border-red-500/30" : "bg-yellow/15 border border-yellow/20"}
        `}
      >
        <FileText
          size={20}
          className={isFailed ? "text-red-400" : "text-yellow"}
          aria-hidden="true"
        />
      </div>

      {/* File info */}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-slate-200">
          {document.filename}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs">
          <span className="text-light-blue/70">{fileType(document.filename)}</span>
          <span className="text-light-blue/30">·</span>

          {/* Status indicator */}
          {isProcessing && <Loader2 size={11} className="animate-spin text-light-blue" aria-hidden="true" />}
          {isComplete && <Check size={12} className="text-emerald-400" aria-hidden="true" />}
          {isFailed && <AlertTriangle size={12} className="text-red-400" aria-hidden="true" />}

          <span className={
            isFailed ? "text-red-400"
            : isComplete ? "text-emerald-400"
            : "text-light-blue/70"
          }>
            {statusLabel[document.status]}
          </span>

          {isComplete && typeof document.chunk_count === "number" && (
            <span className="text-light-blue/40">({document.chunk_count} chunks)</span>
          )}
        </div>
      </div>

      {/* Remove button */}
      <button
        type="button"
        aria-label={`Remove ${document.filename}`}
        onClick={() => onRemove(document.document_id || document.local_id)}
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-light-blue/10 text-slate-400 hover:bg-red-500/15 hover:text-red-400 transition-colors border border-light-blue/15"
      >
        <X size={13} strokeWidth={2.5} aria-hidden="true" />
      </button>
    </div>
  );
}