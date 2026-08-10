"use client";

/** Source verification modal for citations present in the current draft. */

import { useEffect, useId, useMemo, useRef } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  FileText,
  X,
} from "lucide-react";

import type { SourceRef } from "@/lib/api";
import { citationService } from "@/lib/drafting/citationService";
import type { ResolvedCitation, TiptapDocument } from "@/types/drafting";

export interface SourceVerificationPanelProps {
  open: boolean;
  document: TiptapDocument | null;
  sources: SourceRef[];
  activeCitationId?: string | null;
  onClose: () => void;
}

function rowId(citationId: string): string {
  return `draft-source-${citationId.replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

function pageLabel(source: SourceRef): string | null {
  if (source.page_start == null) return null;
  if (source.page_end == null || source.page_end === source.page_start) {
    return `Page ${source.page_start}`;
  }
  return `Pages ${source.page_start}–${source.page_end}`;
}

function displayTitle(citation: ResolvedCitation): string {
  const { source } = citation;
  if (source?.source_type === "user_document" && source.filename) {
    return source.filename;
  }
  return source?.title || citation.attrs.title || citation.citationId;
}

function SourceVerificationRow({
  citation,
  active,
}: {
  citation: ResolvedCitation;
  active: boolean;
}) {
  const { source } = citation;
  const metadata = source
    ? [
        source.section,
        source.year > 0 ? String(source.year) : null,
        source.court,
        pageLabel(source),
      ].filter(Boolean)
    : [];
  const excerpt = source?.excerpt || citation.attrs.excerpt;
  const isDocument = citation.attrs.sourceType === "user_document";

  return (
    <article
      id={rowId(citation.citationId)}
      className={`rounded-lg border p-4 transition-colors ${
        active
          ? "border-[#D4AF37] bg-[#D4AF37]/10"
          : "border-slate-700/60 bg-[#161B28]"
      }`}
      tabIndex={-1}
      aria-label={`Source details for ${citation.citationId}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`mt-0.5 rounded-md p-2 ${
            isDocument
              ? "bg-purple-400/10 text-purple-400"
              : "bg-[#D4AF37]/10 text-[#D4AF37]"
          }`}
          aria-hidden="true"
        >
          {isDocument ? <FileText size={16} /> : <BookOpenCheck size={16} />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                isDocument
                  ? "bg-purple-400/20 text-purple-300"
                  : "bg-[#D4AF37]/20 text-[#D4AF37]"
              }`}
            >
              {citation.citationId}
            </span>
            {citation.status === "linked" ? (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-emerald-400">
                <CheckCircle2 size={11} /> Source linked
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-amber-400">
                <AlertTriangle size={11} /> Metadata missing
              </span>
            )}
            {citation.occurrenceCount > 1 && (
              <span className="text-[10px] text-slate-500">
                Used {citation.occurrenceCount} times
              </span>
            )}
          </div>

          <h3 className="mt-1.5 text-sm font-semibold leading-snug text-slate-100">
            {displayTitle(citation)}
          </h3>

          {metadata.length > 0 && (
            <p className="mt-1 text-[11px] text-slate-400">
              {metadata.join(" · ")}
            </p>
          )}

          {source?.reporter_citation && (
            <p className="mt-1 text-[11px] text-slate-400">
              Reporter citation: {source.reporter_citation}
            </p>
          )}

          <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
            {excerpt || "No source excerpt was returned for this citation."}
          </p>

          {source?.authoritative != null && (
            <p
              className={`mt-2 text-[10px] font-medium ${
                source.authoritative ? "text-emerald-400" : "text-amber-400"
              }`}
            >
              {source.authoritative
                ? "Marked authoritative by the retrieval pipeline"
                : "Not marked authoritative by the retrieval pipeline"}
            </p>
          )}
        </div>
      </div>
    </article>
  );
}

export function SourceVerificationPanel({
  open,
  document,
  sources,
  activeCitationId = null,
  onClose,
}: SourceVerificationPanelProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const citations = useMemo(
    () => citationService.resolveCitations(document, sources),
    [document, sources],
  );
  const linkedCount = citations.filter(
    (citation) => citation.status === "linked",
  ).length;

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = documentGlobalActiveElement();
    closeButtonRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const focusable = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && globalThis.document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        globalThis.document.activeElement === last
      ) {
        event.preventDefault();
        first.focus();
      }
    };

    globalThis.document.addEventListener("keydown", handleKeyDown);
    return () => {
      globalThis.document.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  useEffect(() => {
    if (!open || !activeCitationId) return;
    const row = globalThis.document.getElementById(rowId(activeCitationId));
    row?.scrollIntoView({ block: "nearest" });
    row?.focus({ preventScroll: true });
  }, [activeCitationId, open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/65 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        className="flex max-h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-slate-700 bg-[#1D2530] shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-700/60 px-5 py-4">
          <div>
            <h2 id={titleId} className="text-base font-semibold text-white">
              Verify Sources
            </h2>
            <p id={descriptionId} className="mt-1 text-xs text-slate-400">
              {citations.length === 0
                ? "No citation marks are present in this draft."
                : `${linkedCount} of ${citations.length} unique citations have matching source metadata.`}
            </p>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-slate-400 transition hover:bg-slate-700/60 hover:text-white"
            aria-label="Close source verification"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-5 chat-scroll">
          {citations.length > 0 ? (
            citations.map((citation) => (
              <SourceVerificationRow
                key={citation.citationId}
                citation={citation}
                active={citation.citationId === activeCitationId}
              />
            ))
          ) : (
            <div className="flex min-h-52 flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 text-center">
              <BookOpenCheck size={28} className="text-slate-500" />
              <p className="mt-3 text-sm font-medium text-slate-300">
                No citations to inspect
              </p>
              <p className="mt-1 max-w-sm text-xs text-slate-500">
                Citation anchors such as [LAW-1] and [DOC-1] will appear here
                after they are added to the document.
              </p>
            </div>
          )}
        </div>

        <footer className="border-t border-slate-700/60 px-5 py-3 text-[11px] leading-relaxed text-slate-500">
          “Source linked” confirms that metadata was returned for the citation;
          it does not replace independent verification of authority, currency,
          or legal applicability before filing.
        </footer>
      </div>
    </div>
  );
}

function documentGlobalActiveElement(): HTMLElement | null {
  const activeElement = globalThis.document.activeElement;
  return activeElement instanceof HTMLElement ? activeElement : null;
}
