/** Aggregates raw execution events into the ordered activity timeline. */

import { create } from "zustand";

import type { ActivityStep, StreamEvent } from "@/types/streaming";

interface ActivityStreamState {
  steps: ActivityStep[];
  isStreaming: boolean;
  sessionId: string | null;
  error: string | null;
}

interface ActivityStreamActions {
  processEvent: (event: StreamEvent) => void;
  startStream: (sessionId: string) => void;
  endStream: () => void;
  setError: (error: string) => void;
  reset: () => void;
}

export type ActivityStreamStore = ActivityStreamState & ActivityStreamActions;

const initialState: ActivityStreamState = {
  steps: [],
  isStreaming: false,
  sessionId: null,
  error: null,
};

const processedEventIds = new Set<string>();
let fallbackStepSequence = 0;

export const useActivityStreamStore = create<ActivityStreamStore>((set) => ({
  ...initialState,

  processEvent: (event) => {
    set((state) => {
      if (event.event_id && processedEventIds.has(event.event_id)) return state;
      if (event.event_id) processedEventIds.add(event.event_id);

      const steps = [...state.steps];

      switch (event.event_type) {
        case "stream_start":
          return {
            ...state,
            isStreaming: true,
            sessionId: event.session_id,
            error: null,
          };

        case "step_start": {
          const index = findRunningStep(steps, event.step_name);
          if (index >= 0 && steps[index].status === "running") {
            steps[index] = {
              ...steps[index],
              label: event.step_label || steps[index].label,
              metadata: { ...steps[index].metadata, ...event.metadata },
            };
          } else {
            steps.push(createStep(event, "running"));
          }
          return { ...state, steps };
        }

        case "step_detail": {
          const index = findRunningStep(steps, event.step_name);
          if (index >= 0) {
            steps[index] = {
              ...steps[index],
              details: appendNonEmpty(steps[index].details, event.detail),
              metadata: { ...steps[index].metadata, ...event.metadata },
            };
          }
          return { ...state, steps };
        }

        case "step_done": {
          const index = findRunningStep(steps, event.step_name);
          if (index >= 0) {
            steps[index] = {
              ...steps[index],
              label: event.step_label || steps[index].label,
              status: "done",
              completedAt: event.timestamp,
              metadata: { ...steps[index].metadata, ...event.metadata },
            };
          }
          return { ...state, steps };
        }

        case "step_error": {
          const index = findRunningStep(steps, event.step_name);
          if (index >= 0) {
            steps[index] = {
              ...steps[index],
              label: event.step_label || steps[index].label,
              status: "error",
              details: appendNonEmpty(steps[index].details, event.detail),
              completedAt: event.timestamp,
              metadata: { ...steps[index].metadata, ...event.metadata },
            };
          }
          return { ...state, steps };
        }

        case "sources_found":
          steps.push({
            ...createStep(event, "done", "sources"),
            details: sourceTitles(event.metadata),
            completedAt: event.timestamp,
          });
          return { ...state, steps };

        case "plan_generated": {
          const index = findRunningStep(steps, "supervisor");
          if (index >= 0) {
            steps[index] = {
              ...steps[index],
              metadata: { ...steps[index].metadata, ...event.metadata },
            };
          }
          return { ...state, steps };
        }

        case "final":
          return { ...state, steps, isStreaming: false };

        case "error":
          return {
            ...state,
            steps: failActiveSteps(steps, event.detail, event.timestamp, event),
            isStreaming: false,
            error: event.detail || "Stream execution failed",
          };

        case "heartbeat":
          return state;
      }
    });
  },

  startStream: (sessionId) => {
    processedEventIds.clear();
    fallbackStepSequence = 0;
    set({ steps: [], isStreaming: true, sessionId, error: null });
  },

  endStream: () => set({ isStreaming: false }),

  setError: (error) => {
    set((state) => ({
      isStreaming: false,
      error,
      steps:
        state.error === error
          ? state.steps
          : failActiveSteps(state.steps, error, Date.now() / 1000),
    }));
  },

  reset: () => {
    processedEventIds.clear();
    fallbackStepSequence = 0;
    set({ ...initialState });
  },
}));

function createStep(
  event: StreamEvent,
  status: ActivityStep["status"],
  stepName = event.step_name,
): ActivityStep {
  fallbackStepSequence += 1;
  return {
    id:
      event.event_id ||
      `${event.session_id || "stream"}-${stepName || "step"}-${fallbackStepSequence}`,
    stepName,
    label: event.step_label || humanizeStepName(stepName),
    status,
    details: [],
    metadata: { ...event.metadata },
    startedAt: event.timestamp,
  };
}

function findRunningStep(steps: ActivityStep[], stepName: string): number {
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    if (steps[index].stepName === stepName && steps[index].status === "running") {
      return index;
    }
  }
  for (let index = steps.length - 1; index >= 0; index -= 1) {
    if (steps[index].stepName === stepName) return index;
  }
  return -1;
}

function appendNonEmpty(details: string[], detail: string): string[] {
  const normalized = detail.trim();
  return normalized ? [...details, normalized] : details;
}

function sourceTitles(metadata: Record<string, unknown>): string[] {
  return Array.isArray(metadata.titles)
    ? metadata.titles.filter(
        (title): title is string => typeof title === "string" && title.trim().length > 0,
      )
    : [];
}

function failActiveSteps(
  steps: ActivityStep[],
  detail: string,
  completedAt: number,
  event?: StreamEvent,
): ActivityStep[] {
  let foundRunningStep = false;
  const failed = steps.map((step) => {
    if (step.status !== "running") return step;
    foundRunningStep = true;
    return {
      ...step,
      status: "error" as const,
      details: appendNonEmpty(step.details, detail),
      completedAt,
    };
  });

  if (foundRunningStep) return failed;
  if (!detail.trim()) return failed;

  const fallbackEvent: StreamEvent =
    event ?? {
      event_type: "error",
      session_id: "",
      event_id: "",
      timestamp: completedAt,
      step_name: "stream",
      step_label: "Execution failed",
      step_status: "error",
      detail,
      metadata: {},
    };

  return [
    ...failed,
    {
      ...createStep(fallbackEvent, "error", fallbackEvent.step_name || "stream"),
      details: [detail],
      completedAt,
    },
  ];
}

function humanizeStepName(stepName: string): string {
  const normalized = stepName.replace(/[_-]+/g, " ").trim();
  return normalized
    ? normalized.charAt(0).toUpperCase() + normalized.slice(1)
    : "Processing request";
}
