/** React facade for SSE transport, activity state, and lifecycle cleanup. */

"use client";

import { useCallback, useEffect, useRef } from "react";

import { connectSSE } from "@/lib/sseClient";
import { useActivityStreamStore } from "@/store/activityStreamStore";
import type { ActivityStep } from "@/types/streaming";

export interface UseActivityStreamReturn {
  steps: ActivityStep[];
  isStreaming: boolean;
  error: string | null;
  startStream: <TPayload>(
    endpoint: string,
    payload: TPayload,
  ) => Promise<Record<string, unknown> | null>;
  cancelStream: () => void;
}

export function useActivityStream(): UseActivityStreamReturn {
  const steps = useActivityStreamStore((state) => state.steps);
  const isStreaming = useActivityStreamStore((state) => state.isStreaming);
  const error = useActivityStreamStore((state) => state.error);
  const processEvent = useActivityStreamStore((state) => state.processEvent);
  const storeStartStream = useActivityStreamStore((state) => state.startStream);
  const endStream = useActivityStreamStore((state) => state.endStream);
  const setError = useActivityStreamStore((state) => state.setError);
  const reset = useActivityStreamStore((state) => state.reset);

  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);

  const startStream = useCallback(
    async <TPayload,>(
      endpoint: string,
      payload: TPayload,
    ): Promise<Record<string, unknown> | null> => {
      abortRef.current?.abort();
      const generation = ++generationRef.current;
      reset();

      const controller = new AbortController();
      abortRef.current = controller;
      storeStartStream(createClientSessionId());

      let finalResponse: Record<string, unknown> | null = null;
      let streamError: Error | null = null;

      try {
        await connectSSE({
          endpoint,
          payload,
          signal: controller.signal,
          onEvent: (event) => {
            if (generation === generationRef.current) processEvent(event);
          },
          onComplete: (response) => {
            finalResponse = response;
          },
          onError: (caughtError) => {
            streamError = caughtError;
          },
        });

        if (controller.signal.aborted || generation !== generationRef.current) {
          return null;
        }
        if (streamError) throw streamError;
        if (!finalResponse) {
          throw new Error("Activity stream completed without a final response");
        }

        endStream();
        return finalResponse;
      } catch (caughtError) {
        if (controller.signal.aborted || generation !== generationRef.current) {
          return null;
        }
        const normalizedError =
          caughtError instanceof Error
            ? caughtError
            : new Error("Activity stream failed");
        setError(normalizedError.message);
        throw normalizedError;
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [endStream, processEvent, reset, setError, storeStartStream],
  );

  const cancelStream = useCallback(() => {
    generationRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    endStream();
  }, [endStream]);

  useEffect(
    () => () => {
      generationRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      endStream();
    },
    [endStream],
  );

  return { steps, isStreaming, error, startStream, cancelStream };
}

function createClientSessionId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `stream-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
