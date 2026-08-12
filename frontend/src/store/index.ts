/**
 * Store barrel export — re-exports all Zustand stores for clean imports.
 *
 * Usage:
 *   import { useDraftDocumentStore, useVersionStore, useChatEditStore } from "@/store";
 *
 * @module store/index
 */

export { useDraftDocumentStore } from "./draftDocumentStore";
export type { DraftDocumentStore } from "./draftDocumentStore";

export { useVersionStore } from "./versionStore";
export type { VersionStore } from "./versionStore";

export { useChatEditStore } from "./chatEditStore";
export type { ChatEditStore } from "./chatEditStore";
export type { DraftEditPayload, DraftEditResult } from "./chatEditStore";

export { useConversationStore } from "./conversationStore";
export type { ConversationStore } from "./conversationStore";

export { useActivityStreamStore } from "./activityStreamStore";
export type { ActivityStreamStore } from "./activityStreamStore";
