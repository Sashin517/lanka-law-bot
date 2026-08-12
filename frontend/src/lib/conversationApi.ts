/** Authenticated conversation API Facade. */

import { auth } from "@/lib/firebase/firebase";
import type {
  ConversationDetail,
  ConversationListResponse,
  ConversationSummary,
  MessageAttachment,
  MessageListResponse,
  OperationStatusResponse,
  SendMessageResponse,
} from "@/types/conversation";
import type { QueryMode } from "@/types/QueryMode";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";
const DEFAULT_CONVERSATION_LIMIT = 30;
const DEFAULT_MESSAGE_LIMIT = 50;

export interface AuthTokenProvider {
  getToken: (forceRefresh?: boolean) => Promise<string>;
}

export interface ConversationRequestOptions {
  signal?: AbortSignal;
}

export class ConversationApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown = null) {
    super(message);
    this.name = "ConversationApiError";
    this.status = status;
    this.details = details;
  }
}

class FirebaseAuthTokenProvider implements AuthTokenProvider {
  async getToken(forceRefresh = false): Promise<string> {
    const user = auth.currentUser;
    if (!user) {
      throw new ConversationApiError("Not authenticated", 401);
    }
    try {
      return await user.getIdToken(forceRefresh);
    } catch (error) {
      throw new ConversationApiError(
        error instanceof Error
          ? error.message
          : "Authentication token retrieval failed",
        401,
        error,
      );
    }
  }
}

export class ConversationApiClient {
  private readonly baseUrl: string;
  private readonly tokenProvider: AuthTokenProvider;
  private readonly fetcher: typeof fetch;

  constructor(
    baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE_URL,
    tokenProvider: AuthTokenProvider = new FirebaseAuthTokenProvider(),
    fetcher: typeof fetch = fetch,
  ) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.tokenProvider = tokenProvider;
    this.fetcher = (input, init) => fetcher(input, init);
  }

  createConversation(
    title = "New Chat",
    queryMode: QueryMode = "quick_qa",
    options: ConversationRequestOptions = {},
  ): Promise<ConversationSummary> {
    return this.request<ConversationSummary>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title, query_mode: queryMode }),
      signal: options.signal,
    });
  }

  listConversations(
    cursor: string | null = null,
    limit = DEFAULT_CONVERSATION_LIMIT,
    options: ConversationRequestOptions = {},
  ): Promise<ConversationListResponse> {
    assertIntegerRange(limit, 1, 100, "conversation limit");
    const params = paginationParameters(cursor, limit);
    return this.request<ConversationListResponse>(
      `/api/conversations?${params.toString()}`,
      { signal: options.signal },
    );
  }

  getConversation(
    conversationId: string,
    options: ConversationRequestOptions = {},
  ): Promise<ConversationDetail> {
    return this.request<ConversationDetail>(
      `/api/conversations/${pathSegment(conversationId)}`,
      { signal: options.signal },
    );
  }

  async renameConversation(
    conversationId: string,
    title: string,
    options: ConversationRequestOptions = {},
  ): Promise<void> {
    await this.request<OperationStatusResponse>(
      `/api/conversations/${pathSegment(conversationId)}/title`,
      {
        method: "PATCH",
        body: JSON.stringify({ title }),
        signal: options.signal,
      },
    );
  }

  async deleteConversation(
    conversationId: string,
    options: ConversationRequestOptions = {},
  ): Promise<void> {
    await this.request<OperationStatusResponse>(
      `/api/conversations/${pathSegment(conversationId)}`,
      { method: "DELETE", signal: options.signal },
    );
  }

  listMessages(
    conversationId: string,
    cursor: string | null = null,
    limit = DEFAULT_MESSAGE_LIMIT,
    options: ConversationRequestOptions = {},
  ): Promise<MessageListResponse> {
    assertIntegerRange(limit, 1, 200, "message limit");
    const params = paginationParameters(cursor, limit);
    return this.request<MessageListResponse>(
      `/api/conversations/${pathSegment(conversationId)}/messages?${params.toString()}`,
      { signal: options.signal },
    );
  }

  sendMessage(
    conversationId: string,
    content: string,
    queryMode: QueryMode = "quick_qa",
    documentIds: string[] = [],
    attachments: MessageAttachment[] = [],
    options: ConversationRequestOptions = {},
  ): Promise<SendMessageResponse> {
    return this.request<SendMessageResponse>(
      `/api/conversations/${pathSegment(conversationId)}/messages`,
      {
        method: "POST",
        body: JSON.stringify({
          content,
          query_mode: queryMode,
          document_ids: documentIds,
          attachments,
        }),
        signal: options.signal,
      },
    );
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    let response: Response;
    try {
      response = await this.execute(path, options, false);
      if (response.status === 401) {
        response = await this.execute(path, options, true);
      }
    } catch (error) {
      if (error instanceof ConversationApiError || isAbortError(error)) {
        throw error;
      }
      console.error("Conversation API fetch failed:", error);
      const detail =
        error instanceof Error && error.message ? `: ${error.message}` : "";
      throw new ConversationApiError(
        `Unable to reach the conversation service${detail}`,
        0,
        error,
      );
    }

    let data: unknown;
    try {
      data = await parseResponseBody(response);
    } catch (error) {
      if (error instanceof ConversationApiError || isAbortError(error)) {
        throw error;
      }
      throw new ConversationApiError(
        "Unable to read the conversation service response",
        response.status,
        error,
      );
    }
    if (!response.ok) {
      throw new ConversationApiError(
        responseErrorMessage(data, response.statusText),
        response.status,
        data,
      );
    }
    return data as T;
  }

  private async execute(
    path: string,
    options: RequestInit,
    forceTokenRefresh: boolean,
  ): Promise<Response> {
    const token = await this.tokenProvider.getToken(forceTokenRefresh);
    const headers = new Headers(options.headers);
    headers.set("Accept", "application/json");
    headers.set("Authorization", `Bearer ${token}`);
    if (options.body !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    return this.fetcher(`${this.baseUrl}${path}`, {
      ...options,
      cache: "no-store",
      headers,
    });
  }
}

function paginationParameters(
  cursor: string | null,
  limit: number,
): URLSearchParams {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return params;
}

function pathSegment(value: string): string {
  const normalized = value.trim();
  if (!normalized) throw new TypeError("Conversation ID cannot be empty");
  return encodeURIComponent(normalized);
}

function assertIntegerRange(
  value: number,
  minimum: number,
  maximum: number,
  field: string,
): void {
  if (!Number.isInteger(value) || value < minimum || value > maximum) {
    throw new RangeError(`${field} must be between ${minimum} and ${maximum}`);
  }
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return null;
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    if (response.ok) {
      throw new ConversationApiError(
        "Conversation service returned an invalid response",
        response.status,
      );
    }
    return text;
  }
}

function responseErrorMessage(data: unknown, fallback: string): string {
  if (typeof data === "string" && data.trim()) return data;
  if (data && typeof data === "object") {
    const record = data as Record<string, unknown>;
    for (const key of ["detail", "error", "message"]) {
      if (typeof record[key] === "string" && record[key].trim()) {
        return record[key];
      }
    }
    if (Array.isArray(record.detail)) {
      const messages = record.detail
        .map((item) =>
          item && typeof item === "object"
            ? (item as Record<string, unknown>).msg
            : null,
        )
        .filter((message): message is string => typeof message === "string");
      if (messages.length > 0) return messages.join("; ");
    }
  }
  return fallback || "Conversation request failed";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export const conversationApi = new ConversationApiClient();

export const createConversation =
  conversationApi.createConversation.bind(conversationApi);
export const listConversations =
  conversationApi.listConversations.bind(conversationApi);
export const getConversation =
  conversationApi.getConversation.bind(conversationApi);
export const renameConversation =
  conversationApi.renameConversation.bind(conversationApi);
export const deleteConversation =
  conversationApi.deleteConversation.bind(conversationApi);
export const listMessages = conversationApi.listMessages.bind(conversationApi);
export const sendMessage = conversationApi.sendMessage.bind(conversationApi);
