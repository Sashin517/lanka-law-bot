/**
 * Typed fetch-based SSE adapter.
 *
 * Native EventSource cannot POST JSON request bodies, so this client parses the
 * response stream directly. It deliberately defaults to no reconnect because
 * replaying a POST can execute a workflow twice. Retry is opt-in for endpoints
 * that support Last-Event-ID replay or an equivalent idempotency contract.
 */

import { API_BASE_URL } from "@/lib/api";
import { isStreamEvent, type StreamEvent } from "@/types/streaming";

export interface SSEReconnectOptions {
  /** Number of reconnects after the initial request. Defaults to zero. */
  maxAttempts?: number;
  /** Initial exponential-backoff delay. Defaults to 500 ms. */
  delayMs?: number;
  /** Maximum exponential-backoff delay. Defaults to 5 seconds. */
  maxDelayMs?: number;
}

export interface SSEClientOptions<TPayload> {
  endpoint: string;
  payload: TPayload;
  onEvent: (event: StreamEvent) => void;
  onComplete?: (finalResponse: Record<string, unknown>) => void;
  onError?: (error: Error) => void;
  signal?: AbortSignal;
  reconnect?: SSEReconnectOptions;
  /** Additional request headers, such as an authenticated bearer token. */
  headers?: HeadersInit;
  /** Optional API origin override for injectable clients and tests. */
  baseUrl?: string;
  /** Injectable fetch implementation for API facade tests. */
  fetcher?: typeof fetch;
}

interface NormalizedReconnectOptions {
  maxAttempts: number;
  delayMs: number;
  maxDelayMs: number;
}

export class SSEConnectionError extends Error {
  constructor(
    message: string,
    readonly retryable: boolean,
    readonly lastEventId = "",
    readonly status = 0,
  ) {
    super(message);
    this.name = "SSEConnectionError";
  }
}

class SSEApplicationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SSEApplicationError";
  }
}

export async function connectSSE<TPayload>(
  options: SSEClientOptions<TPayload>,
): Promise<void> {
  const reconnect = normalizeReconnectOptions(options.reconnect);
  const seenEventIds = new Set<string>();
  let lastEventId = "";

  for (let attempt = 0; ; attempt += 1) {
    try {
      lastEventId = await consumeStream(options, seenEventIds, lastEventId);
      return;
    } catch (error) {
      if (options.signal?.aborted || isAbortError(error)) return;

      const normalizedError = toError(error, "SSE stream failed");
      if (
        normalizedError instanceof SSEConnectionError &&
        normalizedError.lastEventId
      ) {
        lastEventId = normalizedError.lastEventId;
      }
      const retryable =
        normalizedError instanceof SSEConnectionError &&
        normalizedError.retryable;

      if (!retryable || attempt >= reconnect.maxAttempts) {
        if (options.onError) {
          options.onError(normalizedError);
          return;
        }
        throw normalizedError;
      }

      const delay = Math.min(
        reconnect.delayMs * 2 ** attempt,
        reconnect.maxDelayMs,
      );
      await abortableDelay(delay, options.signal);
    }
  }
}

async function consumeStream<TPayload>(
  options: SSEClientOptions<TPayload>,
  seenEventIds: Set<string>,
  lastEventId: string,
): Promise<string> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "text/event-stream");
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (lastEventId) headers.set("Last-Event-ID", lastEventId);

  let response: Response;
  try {
    const fetcher = options.fetcher ?? fetch;
    response = await fetcher(buildEndpointUrl(options.endpoint, options.baseUrl), {
      method: "POST",
      headers,
      body: JSON.stringify(options.payload),
      cache: "no-store",
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted || isAbortError(error)) throw error;
    throw new SSEConnectionError(
      "Unable to connect to the activity stream",
      true,
    );
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    throw new SSEConnectionError(
      `SSE connection failed (${response.status}): ${detail}`,
      response.status === 408 ||
        response.status === 425 ||
        response.status === 429 ||
        response.status >= 500,
      "",
      response.status,
    );
  }

  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (contentType && !contentType.includes("text/event-stream")) {
    throw new SSEConnectionError(
      `Expected text/event-stream but received ${contentType}`,
      false,
      "",
      response.status,
    );
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new SSEConnectionError(
      "SSE response body is not readable",
      true,
      "",
      response.status,
    );
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentLastEventId = lastEventId;
  let terminalEventReceived = false;

  try {
    while (!terminalEventReceived) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const parsed = extractCompleteFrames(buffer);
      buffer = parsed.remainder;

      for (const frame of parsed.frames) {
        const result = dispatchFrame(frame, options, seenEventIds);
        if (result.lastEventId) currentLastEventId = result.lastEventId;
        if (result.terminal) {
          terminalEventReceived = true;
          break;
        }
      }
    }

    if (!terminalEventReceived && buffer.trim()) {
      const result = dispatchFrame(buffer, options, seenEventIds);
      if (result.lastEventId) currentLastEventId = result.lastEventId;
      terminalEventReceived = result.terminal;
    }

    if (!terminalEventReceived) {
      throw new SSEConnectionError(
        "Activity stream closed before a final event was received",
        true,
        currentLastEventId,
        response.status,
      );
    }

    await reader.cancel().catch(() => undefined);
    return currentLastEventId;
  } catch (error) {
    if (
      error instanceof SSEApplicationError ||
      options.signal?.aborted ||
      isAbortError(error)
    ) {
      throw error;
    }
    if (error instanceof SSEConnectionError) {
      throw new SSEConnectionError(
        error.message,
        error.retryable,
        currentLastEventId || error.lastEventId,
        error.status,
      );
    }
    throw new SSEConnectionError(
      toError(error, "SSE stream failed").message,
      true,
      currentLastEventId,
      response.status,
    );
  } finally {
    reader.releaseLock();
  }
}

function dispatchFrame<TPayload>(
  frame: string,
  options: SSEClientOptions<TPayload>,
  seenEventIds: Set<string>,
): { terminal: boolean; lastEventId: string } {
  const parsedFrame = parseFrame(frame);
  if (!parsedFrame.data) return { terminal: false, lastEventId: "" };

  let candidate: unknown;
  try {
    candidate = JSON.parse(parsedFrame.data);
  } catch {
    return { terminal: false, lastEventId: "" };
  }

  if (!isStreamEvent(candidate)) {
    return { terminal: false, lastEventId: "" };
  }
  if (parsedFrame.eventType && parsedFrame.eventType !== candidate.event_type) {
    return { terminal: false, lastEventId: "" };
  }

  const eventId = candidate.event_id || parsedFrame.id;
  if (eventId && seenEventIds.has(eventId)) {
    return { terminal: false, lastEventId: eventId };
  }
  if (eventId) seenEventIds.add(eventId);

  try {
    options.onEvent(candidate);
  } catch (error) {
    throw new SSEApplicationError(
      toError(error, "Activity event handler failed").message,
    );
  }

  if (candidate.event_type === "final") {
    if (!candidate.final_response) {
      throw new SSEApplicationError("Final stream event did not include a response");
    }
    try {
      options.onComplete?.(candidate.final_response);
    } catch (error) {
      throw new SSEApplicationError(
        toError(error, "Activity completion handler failed").message,
      );
    }
    return { terminal: true, lastEventId: eventId };
  }
  if (candidate.event_type === "error") {
    throw new SSEApplicationError(candidate.detail || "Stream execution failed");
  }

  return { terminal: false, lastEventId: eventId };
}

function parseFrame(frame: string): {
  eventType: string;
  data: string;
  id: string;
} {
  let eventType = "";
  let id = "";
  const dataLines: string[] = [];

  for (const line of frame.split(/\r\n|\r|\n/)) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    let value = separator < 0 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") eventType = value;
    if (field === "data") dataLines.push(value);
    if (field === "id" && !value.includes("\0")) id = value;
  }

  return { eventType, data: dataLines.join("\n"), id };
}

function extractCompleteFrames(buffer: string): {
  frames: string[];
  remainder: string;
} {
  const frames: string[] = [];
  const delimiter = /\r\n\r\n|\n\n|\r\r/g;
  let start = 0;
  let match: RegExpExecArray | null;

  while ((match = delimiter.exec(buffer)) !== null) {
    frames.push(buffer.slice(start, match.index));
    start = match.index + match[0].length;
  }

  return { frames, remainder: buffer.slice(start) };
}

function buildEndpointUrl(endpoint: string, baseUrl = API_BASE_URL): string {
  if (!endpoint.startsWith("/") || endpoint.startsWith("//")) {
    throw new TypeError("SSE endpoint must be an absolute application path");
  }
  return `${baseUrl.replace(/\/+$/, "")}${endpoint}`;
}

/**
 * Return true only when retrying through the legacy endpoint cannot duplicate
 * an already-started workflow. Runtime/application errors deliberately do not
 * qualify for fallback.
 */
export function isSSEEndpointUnavailableError(error: unknown): boolean {
  return (
    error instanceof SSEConnectionError &&
    [404, 405, 415, 501].includes(error.status) &&
    !error.lastEventId
  );
}

async function readErrorDetail(response: Response): Promise<string> {
  const fallback = response.statusText || "Request failed";
  const body = await response.text().catch(() => "");
  if (!body) return fallback;

  try {
    const parsed = JSON.parse(body) as { detail?: unknown; error?: unknown };
    const detail = parsed.detail ?? parsed.error;
    if (typeof detail === "string" && detail.trim()) return detail;
  } catch {
    // Plain-text responses are useful diagnostics and safe to return below.
  }
  return body.slice(0, 500);
}

function normalizeReconnectOptions(
  options?: SSEReconnectOptions,
): NormalizedReconnectOptions {
  return {
    maxAttempts: boundedInteger(options?.maxAttempts, 0, 0, 10),
    delayMs: boundedInteger(options?.delayMs, 500, 0, 60_000),
    maxDelayMs: boundedInteger(options?.maxDelayMs, 5_000, 0, 60_000),
  };
}

function boundedInteger(
  value: number | undefined,
  fallback: number,
  minimum: number,
  maximum: number,
): number {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new RangeError(`Expected an integer between ${minimum} and ${maximum}`);
  }
  return value;
}

function abortableDelay(delayMs: number, signal?: AbortSignal): Promise<void> {
  if (signal?.aborted) return Promise.reject(abortError());
  if (delayMs === 0) return Promise.resolve();

  return new Promise((resolve, reject) => {
    const onAbort = () => {
      globalThis.clearTimeout(timeout);
      reject(abortError());
    };
    const timeout = globalThis.setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, delayMs);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

function abortError(): Error {
  if (typeof DOMException !== "undefined") {
    return new DOMException("The operation was aborted", "AbortError");
  }
  const error = new Error("The operation was aborted");
  error.name = "AbortError";
  return error;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function toError(error: unknown, fallback: string): Error {
  return error instanceof Error ? error : new Error(fallback);
}
