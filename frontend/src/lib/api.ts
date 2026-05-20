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
  source_type?: string;
  filename?: string | null;
}


export interface LegalQueryPayload {
  question: string;
  mode?: QueryMode;
  document_ids?: string[];
  matter_id?: string | null;
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
