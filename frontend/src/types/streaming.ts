/** Canonical frontend contract for backend execution-stream events. */

export const STREAM_EVENT_TYPES = [
  "stream_start",
  "step_start",
  "step_detail",
  "step_done",
  "step_error",
  "sources_found",
  "plan_generated",
  "final",
  "error",
  "heartbeat",
] as const;

export type StreamEventType = (typeof STREAM_EVENT_TYPES)[number];

export const STREAM_STEP_STATUSES = [
  "pending",
  "running",
  "done",
  "error",
  "skipped",
] as const;

export type StreamStepStatus = (typeof STREAM_STEP_STATUSES)[number];

export interface StreamEvent {
  event_type: StreamEventType;
  session_id: string;
  event_id: string;
  timestamp: number;
  step_name: string;
  step_label: string;
  step_status: StreamStepStatus;
  detail: string;
  metadata: Record<string, unknown>;
  final_response?: Record<string, unknown> | null;
}

export interface ActivityStep {
  id: string;
  stepName: string;
  label: string;
  status: StreamStepStatus;
  details: string[];
  metadata: Record<string, unknown>;
  startedAt: number;
  completedAt?: number;
}

const eventTypes = new Set<string>(STREAM_EVENT_TYPES);
const stepStatuses = new Set<string>(STREAM_STEP_STATUSES);

/** Runtime boundary guard. Invalid or partial frames must never reach the store. */
export function isStreamEvent(value: unknown): value is StreamEvent {
  if (!isRecord(value)) return false;

  return (
    typeof value.event_type === "string" &&
    eventTypes.has(value.event_type) &&
    typeof value.session_id === "string" &&
    typeof value.event_id === "string" &&
    typeof value.timestamp === "number" &&
    Number.isFinite(value.timestamp) &&
    typeof value.step_name === "string" &&
    typeof value.step_label === "string" &&
    typeof value.step_status === "string" &&
    stepStatuses.has(value.step_status) &&
    typeof value.detail === "string" &&
    isRecord(value.metadata) &&
    (value.final_response === undefined ||
      value.final_response === null ||
      isRecord(value.final_response))
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
