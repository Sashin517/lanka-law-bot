/**
 * Container-scoped auto-scroll for live feeds.
 *
 * Unlike Element.scrollIntoView(), this never scrolls the document viewport or
 * unrelated ancestors. It also coalesces rapid stream updates into one animation
 * frame and stops following when the user scrolls away from the bottom.
 */

"use client";

import {
  useCallback,
  useEffect,
  useRef,
  type RefObject,
  type UIEventHandler,
} from "react";

export interface ContainedAutoScroll<T extends HTMLElement> {
  containerRef: RefObject<T | null>;
  onScroll: UIEventHandler<T>;
  scrollToBottom: (force?: boolean) => void;
}

const DEFAULT_BOTTOM_THRESHOLD_PX = 72;

export function useContainedAutoScroll<T extends HTMLElement>(
  bottomThresholdPx = DEFAULT_BOTTOM_THRESHOLD_PX,
): ContainedAutoScroll<T> {
  const containerRef = useRef<T>(null);
  const shouldFollowRef = useRef(true);
  const frameRef = useRef<number | null>(null);

  const onScroll = useCallback<UIEventHandler<T>>(
    (event) => {
      const container = event.currentTarget;
      const distanceFromBottom =
        container.scrollHeight - container.scrollTop - container.clientHeight;
      shouldFollowRef.current = distanceFromBottom <= bottomThresholdPx;
    },
    [bottomThresholdPx],
  );

  const scrollToBottom = useCallback((force = false) => {
    if (!force && !shouldFollowRef.current) return;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);

    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      const container = containerRef.current;
      if (!container) return;

      // Mutate only this scroll container. Smooth animations would queue under
      // high-frequency SSE updates and produce unstable viewport movement.
      container.scrollTop = container.scrollHeight;
      shouldFollowRef.current = true;
    });
  }, []);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  return { containerRef, onScroll, scrollToBottom };
}
