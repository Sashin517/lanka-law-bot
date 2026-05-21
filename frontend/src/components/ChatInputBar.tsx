"use client";

import { FormEvent, useRef, useState } from "react";
import {
  FileSearch,
  PenTool,
  Plus,
  Scale,
  Send,
  Sparkles,
  Telescope,
} from "lucide-react";

import { ChatAttachmentCard } from "@/components/ChatAttachmentCard";
import type { UploadedDocument } from "@/types/documents";
import type { QueryMode } from "@/types/QueryMode";
import { QUERY_MODES } from "@/types/QueryMode";

/** Map icon string names to Lucide components. */
const ICON_MAP: Record<string, React.ElementType> = {
  Telescope,
  PenTool,
  FileSearch,
  Scale,
};

interface ChatInputBarProps {
  value: string;
  isLoading: boolean;
  isImproving: boolean;
  documents: UploadedDocument[];
  selectedMode: QueryMode;
  onChange: (value: string) => void;
  onFileSelected: (file: File) => void;
  onRemoveDocument: (documentId: string) => void;
  onModeChange: (mode: QueryMode) => void;
  onSubmit: () => void;
  onImprove: () => void;
}

const ACCEPTED_FILES =
  ".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown";

export function ChatInputBar({
  value,
  isLoading,
  isImproving,
  documents,
  selectedMode,
  onChange,
  onFileSelected,
  onRemoveDocument,
  onModeChange,
  onSubmit,
  onImprove,
}: ChatInputBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [fileInputKey, setFileInputKey] = useState(0);

  const hasPendingDocument = documents.some(
    (doc) => doc.status === "queued" || doc.status === "processing",
  );
  const hasFailedDocument = documents.some((doc) => doc.status === "failed");
  const canSubmit = Boolean(value.trim()) && !isLoading && !hasPendingDocument && !hasFailedDocument;
  const canImprove =
    Boolean(value.trim()) &&
    !isLoading &&
    !isImproving &&
    !hasPendingDocument &&
    !hasFailedDocument;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSubmit) {
      onSubmit();
    }
  };

  const toggleMode = (mode: QueryMode) => {
    // Toggle: if already selected, revert to quick_qa (default)
    onModeChange(selectedMode === mode ? "quick_qa" : mode);
  };

  return (
    <form
      onSubmit={submit}
      className="mx-auto flex max-w-3xl flex-col rounded-[28px] border border-slate-600/40 bg-[#202020] px-4 py-3 shadow-lg"
    >
      {documents.length > 0 && (
        <div className="mb-3 flex flex-col gap-2">
          {documents.map((doc) => (
            <ChatAttachmentCard
              key={doc.document_id || doc.local_id}
              document={doc}
              onRemove={onRemoveDocument}
            />
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        <input
          key={fileInputKey}
          ref={inputRef}
          type="file"
          accept={ACCEPTED_FILES}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onFileSelected(file);
            setFileInputKey((prev) => prev + 1);
          }}
        />
        <button
          type="button"
          aria-label="Attach document"
          onClick={() => inputRef.current?.click()}
          disabled={isLoading}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-200 transition hover:bg-slate-700/70 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus size={26} strokeWidth={1.8} />
        </button>

        <input
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={
            hasPendingDocument ? "Document is still processing..." : "Ask anything"
          }
          disabled={isLoading}
          className="min-w-0 flex-1 bg-transparent py-2 text-base text-white placeholder:text-slate-400 focus:outline-none disabled:opacity-50"
        />

        <button
          type="button"
          disabled={!canImprove}
          onClick={onImprove}
          className="flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-600 px-3 py-2 text-xs font-semibold text-slate-200 transition hover:bg-slate-700/70 disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Improve prompt"
        >
          <Sparkles size={14} aria-hidden="true" />
          {isImproving ? "Improving..." : "Improve"}
        </button>

        <button
          type="submit"
          disabled={!canSubmit}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#D4AF37] text-[#161B28] transition hover:bg-[#C5A030] disabled:cursor-not-allowed disabled:bg-slate-600 disabled:text-slate-400"
          aria-label="Send message"
        >
          <Send size={17} />
        </button>
      </div>

      {/* ── Mode selector buttons ── */}
      <div className="mt-2 flex items-center gap-1.5 px-1">
        {QUERY_MODES.map((mode) => {
          const Icon = ICON_MAP[mode.icon];
          const isActive = selectedMode === mode.value;
          return (
            <button
              key={mode.value}
              type="button"
              onClick={() => toggleMode(mode.value)}
              disabled={isLoading}
              className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-150
                ${
                  isActive
                    ? "bg-[#D4AF37]/20 text-[#D4AF37] ring-1 ring-[#D4AF37]/40"
                    : "text-slate-400 hover:bg-slate-700/50 hover:text-slate-200"
                }
                disabled:cursor-not-allowed disabled:opacity-50`}
              aria-pressed={isActive}
              aria-label={`${mode.label} mode`}
            >
              {Icon && <Icon size={14} />}
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>

      {(hasPendingDocument || hasFailedDocument) && (
        <div className="mt-2 px-12 text-xs">
          {hasPendingDocument && (
            <span className="text-slate-400">
              Wait until the document is ready before sending the query.
            </span>
          )}
          {hasFailedDocument && (
            <span className="text-red-300">
              Remove failed documents before sending.
            </span>
          )}
        </div>
      )}
    </form>
  );
}


