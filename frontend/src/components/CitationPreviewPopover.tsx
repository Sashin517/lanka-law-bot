"use client";

import { useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronUp } from "lucide-react";

import type { SourceRef } from "@/lib/api";

const POPOVER_WIDTH = 320;
const POPOVER_MAX_HEIGHT = 280;
const VIEWPORT_MARGIN = 8;
const subscribeToHydration = () => () => {};

function calculatePosition(anchorRect: DOMRect): { top: number; left: number } {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  let left = anchorRect.left + anchorRect.width / 2 - POPOVER_WIDTH / 2;
  left = Math.max(
    VIEWPORT_MARGIN,
    Math.min(left, viewportWidth - POPOVER_WIDTH - VIEWPORT_MARGIN),
  );

  const spaceBelow = viewportHeight - anchorRect.bottom - VIEWPORT_MARGIN;
  const spaceAbove = anchorRect.top - VIEWPORT_MARGIN;
  const placeAbove =
    spaceBelow < POPOVER_MAX_HEIGHT + 12 && spaceAbove > spaceBelow;
  const candidateTop = placeAbove
    ? anchorRect.top - POPOVER_MAX_HEIGHT - 8
    : anchorRect.bottom + 8;
  const top = Math.max(
    VIEWPORT_MARGIN,
    Math.min(
      candidateTop,
      viewportHeight - POPOVER_MAX_HEIGHT - VIEWPORT_MARGIN,
    ),
  );

  return { top, left };
}

interface CitationPreviewPopoverProps {
  citationId: string;
  source: SourceRef | undefined;
  anchorRect: DOMRect | null;
  open: boolean;
  isDoc: boolean;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onViewInSources?: () => void;
}

export function CitationPreviewPopover({
  citationId,
  source,
  anchorRect,
  open,
  isDoc,
  onMouseEnter,
  onMouseLeave,
  onViewInSources,
}: CitationPreviewPopoverProps) {
  const [expanded, setExpanded] = useState(false);
  const isHydrated = useSyncExternalStore(
    subscribeToHydration,
    () => true,
    () => false,
  );
  if (!isHydrated || !open || !anchorRect) return null;
  const position = calculatePosition(anchorRect);

  const fullText = source?.content || source?.excerpt || "";
  const hasExpandable =
    Boolean(source?.content) &&
    source!.content!.length > (source?.excerpt?.length ?? 0);

  const accentClass = isDoc
    ? "bg-app-document/20 text-app-document"
    : "bg-app-accent/20 text-app-accent";

  const displayTitle =
    source?.source_type === "user_document" && source.filename
      ? source.filename
      : source?.title;

  const metaParts: string[] = [];
  if (source?.year && source.year > 0) metaParts.push(String(source.year));
  if (source?.section) metaParts.push(source.section);

  return createPortal(
    <div
      role="dialog"
      aria-label={`Source preview for ${citationId}`}
      className="fixed z-[100] rounded-lg border border-app-border/80 bg-app-overlay shadow-2xl shadow-black/50"
      style={{
        top: position.top,
        left: position.left,
        width: POPOVER_WIDTH,
        maxHeight: POPOVER_MAX_HEIGHT,
      }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="flex flex-col max-h-[280px] overflow-hidden">
        <div className="px-3 pt-3 pb-2 border-b border-app-border/50 shrink-0">
          <div className="flex items-start gap-2">
            <span
              className={`text-[10px] font-bold px-1.5 py-0.5 rounded shrink-0 ${accentClass}`}
            >
              {citationId}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-xs font-semibold text-app-primary leading-snug line-clamp-2">
                {displayTitle || "Unknown source"}
              </p>
              {metaParts.length > 0 && (
                <p className="text-[10px] text-app-muted mt-0.5">
                  {metaParts.join(" · ")}
                </p>
              )}
              {source?.breadcrumb && (
                <p className="text-[10px] text-app-subtle mt-0.5 line-clamp-1">
                  {source.breadcrumb}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="px-3 py-2 overflow-y-auto flex-1 min-h-0">
          {!source ? (
            <p className="text-xs text-app-subtle italic">Source not found.</p>
          ) : (
            <>
              <p className="text-xs text-app-tertiary leading-relaxed whitespace-pre-wrap">
                {expanded && fullText ? fullText : source.excerpt || fullText}
              </p>
              {hasExpandable && (
                <button
                  type="button"
                  onClick={() => setExpanded((v) => !v)}
                  className="mt-2 flex items-center gap-1 text-[10px] font-semibold text-app-accent hover:text-app-accent-hover transition"
                >
                  {expanded ? (
                    <>
                      <ChevronUp size={12} />
                      Show excerpt
                    </>
                  ) : (
                    <>
                      <ChevronDown size={12} />
                      Show full source
                    </>
                  )}
                </button>
              )}
            </>
          )}
        </div>

        {onViewInSources && source && (
          <div className="px-3 py-2 border-t border-app-border/50 shrink-0">
            <button
              type="button"
              onClick={onViewInSources}
              className="text-[10px] font-semibold text-app-info hover:text-app-info transition"
            >
              View in Sources
            </button>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
