"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { CitationPreviewPopover } from "@/components/CitationPreviewPopover";
import type { SourceRef } from "@/lib/api";

const CLOSE_DELAY_MS = 150;

function usePrefersHover(): boolean {
  const [prefersHover, setPrefersHover] = useState(true);

  useEffect(() => {
    const mq = window.matchMedia("(hover: hover)");
    setPrefersHover(mq.matches);
    const handler = () => setPrefersHover(mq.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  return prefersHover;
}

interface CitationPillProps {
  citationId: string;
  source: SourceRef | undefined;
  onViewInSources?: () => void;
}

export function CitationPill({
  citationId,
  source,
  onViewInSources,
}: CitationPillProps) {
  const isDoc = citationId.startsWith("[DOC");
  const prefersHover = usePrefersHover();
  const [open, setOpen] = useState(false);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const pillRef = useRef<HTMLSpanElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateAnchor = useCallback(() => {
    if (pillRef.current) {
      setAnchorRect(pillRef.current.getBoundingClientRect());
    }
  }, []);

  const cancelClose = useCallback(() => {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimerRef.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  }, [cancelClose]);

  const openPreview = useCallback(() => {
    cancelClose();
    updateAnchor();
    setOpen(true);
  }, [cancelClose, updateAnchor]);

  const handleMouseEnter = () => {
    if (!prefersHover) return;
    openPreview();
  };

  const handleMouseLeave = () => {
    if (!prefersHover) return;
    scheduleClose();
  };

  const handlePopoverMouseEnter = () => {
    if (!prefersHover) return;
    cancelClose();
  };

  const handlePopoverMouseLeave = () => {
    if (!prefersHover) return;
    scheduleClose();
  };

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (prefersHover) return;
    updateAnchor();
    setOpen((v) => !v);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      updateAnchor();
      setOpen((v) => !v);
    }
    if (e.key === "Escape") {
      setOpen(false);
    }
  };

  useEffect(() => {
    if (!open) return;

    const onScrollOrResize = () => updateAnchor();
    window.addEventListener("scroll", onScrollOrResize, true);
    window.addEventListener("resize", onScrollOrResize);

    return () => {
      window.removeEventListener("scroll", onScrollOrResize, true);
      window.removeEventListener("resize", onScrollOrResize);
    };
  }, [open, updateAnchor]);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (pillRef.current?.contains(target)) return;
      const popover = document.querySelector(
        `[aria-label="Source preview for ${citationId}"]`,
      );
      if (popover?.contains(target)) return;
      setOpen(false);
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, citationId]);

  const pillClass = isDoc
    ? "bg-purple-400/20 text-purple-400 hover:bg-purple-400/30"
    : "bg-[#D4AF37]/20 text-[#D4AF37] hover:bg-[#D4AF37]/30";

  return (
    <>
      <span
        ref={pillRef}
        role="button"
        tabIndex={0}
        aria-expanded={open}
        aria-label={`Citation ${citationId}, show source preview`}
        className={`inline-block text-[10px] font-bold px-1.5 py-0.5 rounded mx-0.5 align-middle cursor-pointer transition ${pillClass}`}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        onFocus={() => {
          if (prefersHover) openPreview();
        }}
        onBlur={() => {
          if (prefersHover) scheduleClose();
        }}
      >
        {citationId}
      </span>
      <CitationPreviewPopover
        citationId={citationId}
        source={source}
        anchorRect={anchorRect}
        open={open}
        isDoc={isDoc}
        onMouseEnter={handlePopoverMouseEnter}
        onMouseLeave={handlePopoverMouseLeave}
        onViewInSources={
          onViewInSources
            ? () => {
                setOpen(false);
                onViewInSources();
              }
            : undefined
        }
      />
    </>
  );
}
