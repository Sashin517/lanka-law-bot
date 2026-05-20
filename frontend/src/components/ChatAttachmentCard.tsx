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
      title={isFailed && document.error ? document.error : document.filename}
      className={`flex w-full max-w-[390px] items-center gap-3 rounded-xl border px-3 py-2.5 ${
        isFailed
          ? "border-red-400/40 bg-red-950/20"
          : "border-slate-600/60 bg-[#202020]"
      }`}
    >
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${
          isFailed ? "bg-red-500" : "bg-[#ff3b44]"
        }`}
      >
        <FileText size={21} className="text-white" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-slate-100">
          {document.filename}
        </div>
        <div className="mt-0.5 flex min-h-5 items-center gap-1.5 text-xs text-slate-300">
          <span>{fileType(document.filename)}</span>
          <span className="text-slate-500">·</span>
          {isProcessing && <Loader2 size={12} className="animate-spin text-slate-300" />}
          {document.status === "completed" && <Check size={13} className="text-emerald-400" />}
          {isFailed && <AlertTriangle size={13} className="text-red-300" />}
          <span className={isFailed ? "text-red-300" : "text-slate-300"}>
            {statusLabel[document.status]}
          </span>
          {document.status === "completed" && typeof document.chunk_count === "number" && (
            <span className="text-slate-500">({document.chunk_count} chunks)</span>
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
