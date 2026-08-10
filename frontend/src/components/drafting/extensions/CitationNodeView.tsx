"use client";

/**
 * React interaction adapter for Tiptap v2 CitationMark DOM elements.
 *
 * Tiptap v2 exposes React node views for Node extensions, but not Mark
 * extensions. This component retains the plan's mark-based document schema
 * and delegates hover, focus, keyboard, and touch interactions from the
 * editor DOM to the existing CitationPreviewPopover React component.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Editor } from "@tiptap/core";

import { CitationPreviewPopover } from "@/components/CitationPreviewPopover";
import type { SourceRef } from "@/lib/api";

const CLOSE_DELAY_MS = 150;
const CITATION_SELECTOR = ".citation-mark[data-citation-id]";

interface ActiveCitation {
  citationId: string;
  anchorRect: DOMRect;
  isDocumentSource: boolean;
}

export interface CitationNodeViewProps {
  editor: Editor;
  sources: SourceRef[];
  onViewInSources?: (citationId: string) => void;
}

function citationElement(
  target: EventTarget | null,
  editorRoot: HTMLElement,
): HTMLElement | null {
  if (!(target instanceof Element)) return null;
  const candidate = target.closest<HTMLElement>(CITATION_SELECTOR);
  return candidate && editorRoot.contains(candidate) ? candidate : null;
}

export function CitationNodeView({
  editor,
  sources,
  onViewInSources,
}: CitationNodeViewProps) {
  const [activeCitation, setActiveCitation] =
    useState<ActiveCitation | null>(null);
  const activeElementRef = useRef<HTMLElement | null>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourcesById = useMemo(
    () => new Map(sources.map((source) => [source.citation_id, source])),
    [sources],
  );
  const openCitationId = activeCitation?.citationId ?? null;

  const cancelScheduledClose = useCallback(() => {
    if (!closeTimerRef.current) return;
    clearTimeout(closeTimerRef.current);
    closeTimerRef.current = null;
  }, []);

  const closePreview = useCallback(() => {
    cancelScheduledClose();
    activeElementRef.current?.setAttribute("aria-expanded", "false");
    activeElementRef.current = null;
    setActiveCitation(null);
  }, [cancelScheduledClose]);

  const scheduleClose = useCallback(() => {
    cancelScheduledClose();
    closeTimerRef.current = setTimeout(closePreview, CLOSE_DELAY_MS);
  }, [cancelScheduledClose, closePreview]);

  const openPreview = useCallback(
    (element: HTMLElement) => {
      cancelScheduledClose();
      activeElementRef.current?.setAttribute("aria-expanded", "false");

      const citationId = element.dataset.citationId;
      if (!citationId) return;
      element.setAttribute("aria-expanded", "true");
      activeElementRef.current = element;
      setActiveCitation({
        citationId,
        anchorRect: element.getBoundingClientRect(),
        isDocumentSource:
          element.dataset.sourceType === "user_document" ||
          citationId.startsWith("[DOC-"),
      });
    },
    [cancelScheduledClose],
  );

  useEffect(() => {
    const editorRoot = editor.view.dom;

    const handleMouseOver = (event: MouseEvent) => {
      if (!window.matchMedia("(hover: hover)").matches) return;
      const element = citationElement(event.target, editorRoot);
      if (element) openPreview(element);
    };

    const handleMouseOut = (event: MouseEvent) => {
      if (!window.matchMedia("(hover: hover)").matches) return;
      const element = citationElement(event.target, editorRoot);
      if (!element) return;
      const nextElement = citationElement(event.relatedTarget, editorRoot);
      if (nextElement === element) return;
      scheduleClose();
    };

    const handleClick = (event: MouseEvent) => {
      if (window.matchMedia("(hover: hover)").matches) return;
      const element = citationElement(event.target, editorRoot);
      if (!element) return;
      event.preventDefault();
      event.stopPropagation();
      if (activeElementRef.current === element) closePreview();
      else openPreview(element);
    };

    const handleFocusIn = (event: FocusEvent) => {
      const element = citationElement(event.target, editorRoot);
      if (element) openPreview(element);
    };

    const handleFocusOut = (event: FocusEvent) => {
      const element = citationElement(event.target, editorRoot);
      if (element) scheduleClose();
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      const element = citationElement(event.target, editorRoot);
      if (!element) return;
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openPreview(element);
      } else if (event.key === "Escape") {
        closePreview();
      }
    };

    editorRoot.addEventListener("mouseover", handleMouseOver);
    editorRoot.addEventListener("mouseout", handleMouseOut);
    editorRoot.addEventListener("click", handleClick);
    editorRoot.addEventListener("focusin", handleFocusIn);
    editorRoot.addEventListener("focusout", handleFocusOut);
    editorRoot.addEventListener("keydown", handleKeyDown);

    return () => {
      editorRoot.removeEventListener("mouseover", handleMouseOver);
      editorRoot.removeEventListener("mouseout", handleMouseOut);
      editorRoot.removeEventListener("click", handleClick);
      editorRoot.removeEventListener("focusin", handleFocusIn);
      editorRoot.removeEventListener("focusout", handleFocusOut);
      editorRoot.removeEventListener("keydown", handleKeyDown);
      cancelScheduledClose();
      activeElementRef.current?.setAttribute("aria-expanded", "false");
    };
  }, [
    cancelScheduledClose,
    closePreview,
    editor,
    openPreview,
    scheduleClose,
  ]);

  useEffect(() => {
    if (!openCitationId) return;

    const updateAnchor = () => {
      const element = activeElementRef.current;
      if (!element?.isConnected) {
        closePreview();
        return;
      }
      setActiveCitation((current) =>
        current
          ? { ...current, anchorRect: element.getBoundingClientRect() }
          : null,
      );
    };

    window.addEventListener("scroll", updateAnchor, true);
    window.addEventListener("resize", updateAnchor);
    return () => {
      window.removeEventListener("scroll", updateAnchor, true);
      window.removeEventListener("resize", updateAnchor);
    };
  }, [closePreview, openCitationId]);

  useEffect(() => {
    if (!openCitationId) return;
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (activeElementRef.current?.contains(target)) return;
      if (target instanceof Element && target.closest('[role="dialog"]')) return;
      closePreview();
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, [closePreview, openCitationId]);

  if (!activeCitation) return null;

  return (
    <CitationPreviewPopover
      citationId={activeCitation.citationId}
      source={sourcesById.get(activeCitation.citationId)}
      anchorRect={activeCitation.anchorRect}
      open
      isDoc={activeCitation.isDocumentSource}
      onMouseEnter={cancelScheduledClose}
      onMouseLeave={scheduleClose}
      onViewInSources={
        onViewInSources
          ? () => {
              const citationId = activeCitation.citationId;
              closePreview();
              onViewInSources(citationId);
            }
          : undefined
      }
    />
  );
}
