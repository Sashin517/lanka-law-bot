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
  const canImprove = Boolean(value.trim()) && !isLoading && !isImproving && !hasPendingDocument && !hasFailedDocument;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (canSubmit) onSubmit();
  };

  const toggleMode = (mode: QueryMode) => {
    onModeChange(selectedMode === mode ? "quick_qa" : mode);
  };

  return (
    <form
      onSubmit={submit}
      /* ── Design system tokens ──
         bg-background: global app token (was hardcoded #202020)
         border-light-blue/20: system border (was border-slate-600/40)
         rounded-2xl matches the card radius language of login/signup    */
      className="mx-auto flex max-w-3xl flex-col rounded-2xl border border-light-blue/20 bg-background px-4 py-3 shadow-lg focus-within:border-light-blue/40 transition-colors"
    >
      {/* Attached document cards */}
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

      {/* Main input row */}
      <div className="flex items-center gap-3">
        {/* Hidden file input */}
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

        {/* Attach button
            hover:bg-light-blue/10 — consistent hover token */}
        <button
          type="button"
          aria-label="Attach document"
          onClick={() => inputRef.current?.click()}
          disabled={isLoading}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-slate-400 hover:text-slate-200 hover:bg-light-blue/10 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Plus size={22} strokeWidth={1.8} aria-hidden="true" />
        </button>

        {/* Text input */}
        <input
          type="text"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={hasPendingDocument ? "Document is processing…" : "Ask anything about Sri Lankan law…"}
          disabled={isLoading}
          className="min-w-0 flex-1 bg-transparent py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
        />

        {/* Improve prompt button
            border-light-blue/30: system border token */}
        <button
          type="button"
          disabled={!canImprove}
          onClick={onImprove}
          className="flex shrink-0 items-center gap-1.5 rounded-xl border border-light-blue/30 px-3 py-2 text-xs font-medium text-slate-300 hover:text-slate-100 hover:bg-light-blue/10 hover:border-light-blue/50 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
          aria-label="Improve prompt with AI"
        >
          <Sparkles size={13} aria-hidden="true" />
          {isImproving ? "Improving…" : "Improve"}
        </button>

        {/* Send button
            bg-yellow text-dark-blue: primary CTA (matches login button)
            disabled: bg-light-blue/20 muted state */}
        <button
          type="submit"
          disabled={!canSubmit}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-yellow text-dark-blue hover:bg-yellow/90 active:scale-95 transition-all disabled:cursor-not-allowed disabled:bg-light-blue/20 disabled:text-slate-500 shadow-sm"
          aria-label="Send message"
        >
          <Send size={16} aria-hidden="true" />
        </button>
      </div>

      {/* ── Mode selector ──
          Active: yellow accent bg + yellow text + yellow ring (system CTA)
          Inactive: slate-500 text, light-blue hover
          Consistent with the tab-style nav in the header               */}
      <div className="mt-2.5 flex items-center gap-1.5 px-1 flex-wrap">
        {QUERY_MODES.map((mode) => {
          const Icon = ICON_MAP[mode.icon];
          const isActive = selectedMode === mode.value;
          return (
            <button
              key={mode.value}
              type="button"
              onClick={() => toggleMode(mode.value)}
              disabled={isLoading}
              className={`
                flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-all duration-150
                ${isActive
                  ? "bg-yellow/15 text-yellow ring-1 ring-yellow/30 border border-yellow/20"
                  : "text-slate-500 hover:bg-light-blue/10 hover:text-slate-300 border border-transparent"
                }
                disabled:cursor-not-allowed disabled:opacity-50
              `}
              aria-pressed={isActive}
              aria-label={`${mode.label} mode`}
            >
              {Icon && <Icon size={13} aria-hidden="true" />}
              <span>{mode.label}</span>
            </button>
          );
        })}
      </div>

      {/* Status hints */}
      {(hasPendingDocument || hasFailedDocument) && (
        <div className="mt-2 px-1 text-xs">
          {hasPendingDocument && (
            <span className="text-slate-500">
              Waiting for document to finish processing…
            </span>
          )}
          {hasFailedDocument && (
            <span className="text-red-400">
              Remove the failed document before sending.
            </span>
          )}
        </div>
      )}
    </form>
  );
}