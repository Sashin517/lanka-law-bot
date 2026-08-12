/** Backend wire contracts for persistent research conversations. */

import type { LegalQueryResponse, SourceRef } from "@/lib/api";
import type { QueryMode } from "@/types/QueryMode";

export type ConversationStatus = "active" | "archived";
export type ConversationRole = "user" | "assistant" | "system";

export interface ConversationSummary {
  id: string;
  title: string;
  query_mode: QueryMode;
  message_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  citation_id: string;
  title: string;
  section: string | null;
  year: number;
  breadcrumb: string | null;
  excerpt: string;
  source_type: string | null;
  document_id: string | null;
  filename: string | null;
  page_start: number | null;
  page_end: number | null;
  source_uri: string | null;
  court: string | null;
  reporter_citation: string | null;
  docket_number: string | null;
  authoritative: boolean | null;
}

export interface MessageAttachment {
  document_id: string;
  filename: string;
  status: string;
}

export interface ConversationMessage {
  id: string;
  role: ConversationRole;
  content: string;
  markdown_content: string | null;
  confidence: string | null;
  disclaimer: string | null;
  sequence_number: number;
  query_mode: QueryMode | null;
  citations: Citation[];
  attachments: MessageAttachment[];
  created_at: string;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  next_cursor: string | null;
}

export interface MessageListResponse {
  messages: ConversationMessage[];
  next_cursor: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  status: ConversationStatus;
  messages: MessageListResponse;
}

export interface OperationStatusResponse {
  status: "ok";
}

export interface CreateConversationPayload {
  title?: string;
  query_mode?: QueryMode;
}

export interface RenameConversationPayload {
  title: string;
}

export interface SendMessagePayload {
  content: string;
  query_mode?: QueryMode;
  document_ids?: string[];
  attachments?: MessageAttachment[];
}

export interface ConversationAgentResponse extends LegalQueryResponse {
  sources?: SourceRef[];
  [key: string]: unknown;
}

export interface SendMessageResponse {
  user_message: ConversationMessage;
  assistant_message: ConversationMessage;
  response: ConversationAgentResponse;
}
