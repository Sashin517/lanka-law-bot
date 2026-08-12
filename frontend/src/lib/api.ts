import type {
  DocumentStatusResponse,
  UploadDocumentResponse,
} from "@/types/documents";
import type { QueryMode } from "@/types/QueryMode";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export interface SourceRef {
  citation_id: string;
  title: string;
  section: string | null;
  year: number;
  breadcrumb: string | null;
  excerpt: string;
  content?: string;
  source_type?: string | null;
  document_id?: string | null;
  filename?: string | null;
  page_start?: number | null;
  page_end?: number | null;
  source_uri?: string | null;
  court?: string | null;
  reporter_citation?: string | null;
  docket_number?: string | null;
  authoritative?: boolean | null;
}


export interface LegalQueryPayload {
  question: string;
  mode?: QueryMode;
  document_ids?: string[];
  matter_id?: string | null;
}

export interface ImprovePromptPayload {
  draft: string;
  mode: QueryMode;
  has_documents?: boolean;
}

export interface ExecutionStepTrace {
  agent: string;
  purpose: string;
}

export interface ExecutionTrace {
  plan_type: "fast_path" | "planned";
  steps_executed: ExecutionStepTrace[];
  total_steps: number;
  planning_reasoning: string;
  completed_agents: string[];
}

export interface LegalQueryResponse {
  answer?: string;                // Plain text fallback
  markdown_content?: string;      // Rich markdown for rendering
  sources?: SourceRef[];
  confidence?: string;
  disclaimer?: string;
  grounding_score?: number;
  route?: {
    route: string;
    task_type: string;
    answer_mode: string;
  };
  execution_trace?: ExecutionTrace;
}

export interface ImprovePromptResponse {
  improved_prompt: string;
  intent_summary?: string | null;
}

async function parseJsonOrThrow<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail ?? data?.error ?? response.statusText;
    throw new Error(typeof detail === "string" ? detail : "Request failed");
  }
  return data as T;
}

export async function uploadDocument(
  file: File,
): Promise<UploadDocumentResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/api/documents/upload`, {
    method: "POST",
    body: formData,
  });

  return parseJsonOrThrow<UploadDocumentResponse>(response);
}

export async function getDocumentStatus(
  documentId: string,
): Promise<DocumentStatusResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/documents/${documentId}/status`,
  );
  return parseJsonOrThrow<DocumentStatusResponse>(response);
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/documents/${documentId}`, {
    method: "DELETE",
  });
  await parseJsonOrThrow(response);
}

export async function sendLegalQuery(
  payload: LegalQueryPayload,
): Promise<LegalQueryResponse> {
  const response = await fetch(`${API_BASE_URL}/api/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return parseJsonOrThrow<LegalQueryResponse>(response);
}

export async function improvePrompt(
  payload: ImprovePromptPayload,
): Promise<ImprovePromptResponse> {
  const response = await fetch(`${API_BASE_URL}/api/prompt/improve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return parseJsonOrThrow<ImprovePromptResponse>(response);
}

// ─── Draft Editing API ──────────────────────────────────────────

export interface DraftEditPayload {
  draft_id: string;
  instruction: string;
  selected_text: string | null;
  selection_start: number | null;
  selection_end: number | null;
  current_content: string;
  document_ids: string[];
}

/**
 * Result from `/api/draft/edit` — supports both light and heavy paths.
 *
 * - `edit_path: "light"` → standalone service (~2-3s), no execution_trace.
 * - `edit_path: "heavy"` → full LangGraph pipeline (~8-15s), includes trace.
 */
export interface DraftEditResult {
  edit_type: string;
  original_text: string;
  edited_text: string;
  markdown_content: string;
  sources: SourceRef[];
  edit_summary: string;
  confidence: string;
  edit_path: "light" | "heavy";
  execution_trace?: ExecutionTrace | null;
}

/**
 * Send a targeted edit request to the backend.
 *
 * The backend's edit classifier decides whether to use the light path
 * (standalone service, ~2-3s) or the heavy path (full LangGraph
 * pipeline, ~8-15s). The frontend does NOT need to specify the path.
 */
export async function editDraft(
  payload: DraftEditPayload,
): Promise<DraftEditResult> {
  const response = await fetch(`${API_BASE_URL}/api/draft/edit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  return parseJsonOrThrow<DraftEditResult>(response);
}
