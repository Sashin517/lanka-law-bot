export type DocumentStatus = "queued" | "processing" | "completed" | "failed";

export interface UploadedDocument {
  document_id: string;
  job_id: string;
  filename: string;
  status: DocumentStatus;
  chunk_count?: number;
  error?: string | null;
  file?: File;
  local_id: string;
  uploaded_at: string;
}

export interface UploadDocumentResponse {
  document_id: string;
  job_id: string;
  filename: string;
  status: "queued";
}

export interface DocumentStatusResponse {
  document_id: string;
  job_id: string | null;
  filename: string;
  status: DocumentStatus;
  chunk_count: number;
  error: string | null;
}

export interface AttachedDocument {
  document_id: string;
  filename: string;
  status: DocumentStatus;
}
