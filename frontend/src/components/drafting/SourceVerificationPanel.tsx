"use client";

/** Embedded source-verification view for the drafting sidebar. */

import { useEffect, useMemo, useRef } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle2,
  FileText,
} from "lucide-react";

import type { SourceRef } from "@/lib/api";
import { citationService } from "@/lib/drafting/citationService";
import type { ResolvedCitation, TiptapDocument } from "@/types/drafting";

export interface SourceVerificationPanelProps {
  document: TiptapDocument | null;
  sources: SourceRef[];
  activeCitationId?: string | null;
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
      className={`rounded-lg border p-3 transition-colors ${
        active
          ? "border-[#D4AF37] bg-[#D4AF37]/10"
          : "border-slate-700/60 bg-[#1D2530]/70"
      }`}
      tabIndex={-1}
      aria-label={`Source details for ${citation.citationId}`}
    >
      <div className="flex items-start gap-2.5">
        <div
          className={`mt-0.5 shrink-0 rounded-md p-1.5 ${
            isDocument
              ? "bg-purple-400/10 text-purple-400"
              : "bg-[#D4AF37]/10 text-[#D4AF37]"
          }`}
          aria-hidden="true"
        >
          {isDocument ? <FileText size={14} /> : <BookOpenCheck size={14} />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span
              className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                isDocument
                  ? "bg-purple-400/20 text-purple-300"
                  : "bg-[#D4AF37]/20 text-[#D4AF37]"
              }`}
            >
              {citation.citationId}
            </span>
            {citation.status === "linked" ? (
              <span className="inline-flex items-center gap-1 text-[9px] font-medium text-emerald-400">
                <CheckCircle2 size={10} /> Linked
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-[9px] font-medium text-amber-400">
                <AlertTriangle size={10} /> Metadata missing
              </span>
            )}
          </div>

          <h3 className="mt-1.5 break-words text-xs font-semibold leading-snug text-slate-100">
            {displayTitle(citation)}
          </h3>

          {metadata.length > 0 && (
            <p className="mt-1 text-[10px] leading-relaxed text-slate-400">
              {metadata.join(" · ")}
            </p>
          )}

          {source?.reporter_citation && (
            <p className="mt-1 break-words text-[10px] text-slate-400">
              Reporter: {source.reporter_citation}
            </p>
          )}

          <p className="mt-2 whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">
            {excerpt || "No source excerpt was returned for this citation."}
          </p>

          <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 text-[9px] text-slate-500">
            {citation.occurrenceCount > 1 && (
              <span>Used {citation.occurrenceCount} times</span>
            )}
            {source?.authoritative != null && (
              <span
                className={
                  source.authoritative ? "text-emerald-400" : "text-amber-400"
                }
              >
                {source.authoritative ? "Marked authoritative" : "Not marked authoritative"}
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

export function SourceVerificationPanel({
  document,
  sources,
  activeCitationId = null,
}: SourceVerificationPanelProps) {
  const panelRef = useRef<HTMLElement>(null);
  const citations = useMemo(
    () => citationService.resolveCitations(document, sources),
    [document, sources],
  );
  const linkedCount = citations.filter(
    (citation) => citation.status === "linked",
  ).length;

  useEffect(() => {
    if (!activeCitationId) return;
    const row = panelRef.current?.querySelector<HTMLElement>(
      `#${rowId(activeCitationId)}`,
    );
    row?.scrollIntoView({ block: "nearest" });
    row?.focus({ preventScroll: true });
  }, [activeCitationId]);

  return (
    <section
      ref={panelRef}
      className="flex min-h-0 w-full flex-1 flex-col overflow-hidden"
      aria-label="Source verification"
    >
      <header className="border-b border-slate-700/50 px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpenCheck size={13} className="text-[#D4AF37]" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Verify Sources
          </h2>
        </div>
        <p className="mt-1.5 text-[10px] leading-relaxed text-slate-500">
          {citations.length === 0
            ? "No citation marks are present in this draft."
            : `${linkedCount} of ${citations.length} unique citations have matching metadata.`}
        </p>
      </header>

      <div className="flex-1 space-y-2.5 overflow-y-auto p-3 chat-scroll">
        {citations.length > 0 ? (
          citations.map((citation) => (
            <SourceVerificationRow
              key={citation.citationId}
              citation={citation}
              active={citation.citationId === activeCitationId}
            />
          ))
        ) : (
          <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-slate-700 px-4 text-center">
            <BookOpenCheck size={24} className="text-slate-500" />
            <p className="mt-3 text-xs font-medium text-slate-300">
              No citations to inspect
            </p>
            <p className="mt-1 text-[10px] leading-relaxed text-slate-500">
              Citation anchors such as [LAW-1] and [DOC-1] will appear here.
            </p>
          </div>
        )}
      </div>

      <footer className="border-t border-slate-700/60 px-3 py-2.5 text-[9px] leading-relaxed text-slate-500">
        “Linked” confirms matching metadata. Independently verify authority,
        currency, and legal applicability before filing.
      </footer>
    </section>
  );
}
