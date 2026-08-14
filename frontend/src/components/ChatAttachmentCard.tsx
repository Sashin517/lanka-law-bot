"use client";

import { AlertTriangle, Check, FileText, Loader2, X } from "lucide-react";

import type { UploadedDocument } from "@/types/documents";

interface ChatAttachmentCardProps {
  document: UploadedDocument;
  onRemove: (documentId: string) => void;
}

const statusLabel: Record<UploadedDocument["status"], string> = {
  queued: "Queued",
  processing: "Processing",
  completed: "Ready",
  failed: "Failed",
};

function fileType(filename: string): string {
  const ext = filename.split(".").pop()?.toUpperCase();
  return ext || "FILE";
}

export function ChatAttachmentCard({ document, onRemove }: ChatAttachmentCardProps) {
  const isProcessing = document.status === "queued" || document.status === "processing";
  const isFailed = document.status === "failed";

  return (
    <div
      role="listitem"
      title={isFailed && document.error ? document.error : document.filename}
      className={`flex w-72 max-w-full shrink-0 items-center gap-3 rounded-xl border px-3 py-2.5 ${
        isFailed
          ? "border-app-danger/40 bg-app-danger/20"
          : "border-app-border/60 bg-app-input"
      }`}
    >
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
          isFailed ? "bg-app-danger" : "bg-[#ff3b44]"
        }`}
      >
        <FileText size={21} className="text-app-strong" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-app-primary">
          {document.filename}
        </div>
        <div className="mt-0.5 flex min-h-5 items-center gap-1.5 text-xs text-app-tertiary">
          <span>{fileType(document.filename)}</span>
          <span className="text-app-subtle">·</span>
          {isProcessing && <Loader2 size={12} className="animate-spin text-app-tertiary" />}
          {document.status === "completed" && <Check size={13} className="text-app-success" />}
          {isFailed && <AlertTriangle size={13} className="text-app-danger" />}
          <span className={isFailed ? "text-app-danger" : "text-app-tertiary"}>
            {statusLabel[document.status]}
          </span>
          {document.status === "completed" && typeof document.chunk_count === "number" && (
            <span className="text-app-subtle">({document.chunk_count} chunks)</span>
          )}
        </div>
      </div>

      <button
        type="button"
        aria-label="Remove attached document"
        onClick={() => onRemove(document.document_id || document.local_id)}
        className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white text-[#202020] transition hover:bg-slate-200"
      >
        <X size={15} strokeWidth={3} />
      </button>
    </div>
  );
}
