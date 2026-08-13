"use client";

import {
  LoaderCircle,
  MessageSquare,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

import { useAuth } from "@/contexts/AuthProvider";
import { useConversationStore } from "@/store/conversationStore";

interface ChatHistorySidebarProps {
  onNewChat: () => void | Promise<void>;
}

export function ChatHistorySidebar({ onNewChat }: ChatHistorySidebarProps) {
  const { user, loading: authLoading } = useAuth();
  const conversations = useConversationStore((state) => state.conversations);
  const activeConversationId = useConversationStore(
    (state) => state.activeConversationId,
  );
  const isListLoading = useConversationStore((state) => state.isListLoading);
  const isCreating = useConversationStore((state) => state.isCreating);
  const hasMore = useConversationStore(
    (state) => state.hasMoreConversations,
  );
  const error = useConversationStore((state) => state.error);
  const loadConversations = useConversationStore(
    (state) => state.loadConversations,
  );
  const loadMore = useConversationStore(
    (state) => state.loadMoreConversations,
  );
  const selectConversation = useConversationStore(
    (state) => state.selectConversation,
  );
  const rename = useConversationStore((state) => state.rename);
  const remove = useConversationStore((state) => state.remove);
  const clearError = useConversationStore((state) => state.clearError);
  const reset = useConversationStore((state) => state.reset);

  const [searchQuery, setSearchQuery] = useState("");
  const [menuId, setMenuId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draftTitle, setDraftTitle] = useState("");
  const [mutatingId, setMutatingId] = useState<string | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLElement>(null);
  const cancelEditRef = useRef(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) {
      reset();
      return;
    }
    void loadConversations();
  }, [authLoading, loadConversations, reset, user]);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel || !user) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && hasMore && !isListLoading) {
          void loadMore();
        }
      },
      { root: sidebarRef.current, rootMargin: "120px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, isListLoading, loadMore, user]);

  useEffect(() => {
    const closeMenu = (event: MouseEvent) => {
      if (
        event.target instanceof Element &&
        !event.target.closest("[data-chat-actions]")
      ) {
        setMenuId(null);
      }
    };
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setMenuId(null);
    };
    document.addEventListener("mousedown", closeMenu);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeMenu);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, []);

  const filteredConversations = useMemo(() => {
    const normalized = searchQuery.trim().toLocaleLowerCase();
    if (!normalized) return conversations;
    return conversations.filter((conversation) =>
      conversation.title.toLocaleLowerCase().includes(normalized),
    );
  }, [conversations, searchQuery]);

  const beginRename = (conversationId: string, title: string) => {
    setMenuId(null);
    setEditingId(conversationId);
    setDraftTitle(title);
    cancelEditRef.current = false;
  };

  const finishRename = async (conversationId: string) => {
    if (cancelEditRef.current) {
      cancelEditRef.current = false;
      return;
    }
    const normalized = draftTitle.replace(/\s+/g, " ").trim();
    if (!normalized) {
      setEditingId(null);
      return;
    }
    setMutatingId(conversationId);
    try {
      await rename(conversationId, normalized);
      setEditingId(null);
    } catch {
      // The store exposes the mutation error in the dismissible error panel.
    } finally {
      setMutatingId(null);
    }
  };

  const handleRenameKeyDown = (
    event: KeyboardEvent<HTMLInputElement>,
  ) => {
    if (event.key === "Enter") event.currentTarget.blur();
    if (event.key === "Escape") {
      cancelEditRef.current = true;
      setEditingId(null);
      event.currentTarget.blur();
    }
    if (event.key === "Escape" || event.key === "Enter") {
      event.preventDefault();
      event.stopPropagation();
    }
  };

  const deleteChat = async (conversationId: string, title: string) => {
    setMenuId(null);
    if (!window.confirm(`Delete “${title}”? This chat will be removed.`)) return;
    setMutatingId(conversationId);
    try {
      await remove(conversationId);
    } catch {
      // The store exposes the mutation error in the dismissible error panel.
    } finally {
      setMutatingId(null);
    }
  };

  return (
    <aside
      ref={sidebarRef}
      aria-label="Chat history"
      className="chat-scroll flex w-[280px] shrink-0 flex-col overflow-y-auto border-r border-app-border/40 bg-app-panel p-4 text-app-strong"
    >
      <button
        type="button"
        onClick={() => {
          void Promise.resolve(onNewChat()).catch(() => undefined);
        }}
        disabled={!user || isCreating}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-app-accent px-4 py-2.5 text-sm font-bold text-app-accent-contrast transition hover:bg-app-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
      >
        {isCreating ? (
          <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />
        ) : (
          <Plus aria-hidden="true" className="size-4" />
        )}
        New Chat
      </button>

      <label className="relative mt-4 block">
        <span className="sr-only">Search chats</span>
        <Search
          aria-hidden="true"
          className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-app-subtle"
        />
        <input
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search chats"
          className="w-full rounded-lg border border-app-border bg-app-panel-muted py-2 pl-9 pr-3 text-sm text-app-primary outline-none transition placeholder:text-app-subtle focus:border-app-accent"
        />
      </label>

      {error && (
        <button
          type="button"
          onClick={clearError}
          className="mt-3 rounded-md border border-app-danger/30 bg-app-danger/10 px-3 py-2 text-left text-xs text-app-danger"
          title="Dismiss error"
        >
          {error}
        </button>
      )}

      <div className="mt-4 flex items-center justify-between px-1">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-app-muted">
          Recent chats
        </h2>
        <span className="text-[10px] text-app-faint">{conversations.length}</span>
      </div>

      <div className="mt-2 space-y-1">
        {(authLoading || (isListLoading && conversations.length === 0)) &&
          Array.from({ length: 5 }, (_, index) => (
            <div
              key={index}
              aria-hidden="true"
              className="animate-pulse rounded-lg bg-app-elevated/40 p-3"
            >
              <div className="h-3 w-3/4 rounded bg-app-hover" />
              <div className="mt-2 h-2 w-full rounded bg-app-elevated" />
            </div>
          ))}

        {!authLoading && user && !isListLoading && conversations.length === 0 && (
          <div className="flex flex-col items-center px-4 py-12 text-center">
            <MessageSquare aria-hidden="true" className="size-8 text-app-faint" />
            <p className="mt-3 text-sm font-medium text-app-tertiary">No chats yet</p>
            <p className="mt-1 text-xs leading-relaxed text-app-subtle">
              Start a new legal research conversation.
            </p>
          </div>
        )}

        {conversations.length > 0 && filteredConversations.length === 0 && (
          <p className="px-3 py-8 text-center text-xs text-app-subtle">
            No chat titles match your search.
          </p>
        )}

        {filteredConversations.map((conversation) => {
          const isActive = conversation.id === activeConversationId;
          const isMutating = conversation.id === mutatingId;
          return (
            <div
              key={conversation.id}
              className={`group relative rounded-lg border transition ${
                isActive
                  ? "border-app-accent/50 bg-app-accent/10"
                  : "border-transparent hover:bg-app-elevated/50"
              }`}
            >
              {editingId === conversation.id ? (
                <div className="w-full px-3 py-2.5 pr-9">
                  <input
                    autoFocus
                    value={draftTitle}
                    maxLength={512}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => setDraftTitle(event.target.value)}
                    onBlur={() => void finishRename(conversation.id)}
                    onKeyDown={(event) =>
                      handleRenameKeyDown(event)
                    }
                    className="w-full rounded border border-app-accent bg-app-overlay px-2 py-1 text-sm text-app-strong outline-none"
                    aria-label="Rename chat"
                  />
                  <p className="mt-1 truncate text-xs text-app-subtle">
                    {conversation.last_message_preview || "No messages yet"}
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    setMenuId(null);
                    void selectConversation(conversation.id);
                  }}
                  disabled={isMutating}
                  aria-current={isActive ? "page" : undefined}
                  className="w-full px-3 py-2.5 pr-9 text-left disabled:opacity-50"
                >
                  <p className="truncate text-sm font-medium text-app-secondary">
                    {conversation.title}
                  </p>
                  <p className="mt-1 truncate text-xs text-app-subtle">
                    {conversation.last_message_preview || "No messages yet"}
                  </p>
                  <p className="mt-1 text-[10px] text-app-faint">
                    {formatTimestamp(conversation.updated_at)}
                  </p>
                </button>
              )}

              {editingId !== conversation.id && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    setMenuId((current) =>
                      current === conversation.id ? null : conversation.id,
                    );
                  }}
                  aria-label={`Actions for ${conversation.title}`}
                  aria-expanded={menuId === conversation.id}
                  data-chat-actions
                  className="absolute right-1.5 top-2 rounded p-1 text-app-subtle opacity-0 transition hover:bg-app-hover hover:text-app-strong focus:opacity-100 group-hover:opacity-100"
                >
                  <MoreHorizontal aria-hidden="true" className="size-4" />
                </button>
              )}

              {menuId === conversation.id && (
                <div
                  data-chat-actions
                  className="absolute right-2 top-9 z-20 w-32 rounded-lg border border-app-border bg-app-overlay p-1 shadow-xl"
                >
                  <button
                    type="button"
                    onClick={() => beginRename(conversation.id, conversation.title)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-app-secondary hover:bg-app-hover"
                  >
                    <Pencil aria-hidden="true" className="size-3.5" /> Rename
                  </button>
                  <button
                    type="button"
                    onClick={() => void deleteChat(conversation.id, conversation.title)}
                    className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-app-danger hover:bg-app-danger/10"
                  >
                    <Trash2 aria-hidden="true" className="size-3.5" /> Delete
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div ref={sentinelRef} className="h-2" aria-hidden="true" />
      {isListLoading && conversations.length > 0 && (
        <LoaderCircle
          aria-label="Loading more chats"
          className="mx-auto my-3 size-4 animate-spin text-app-subtle"
        />
      )}
    </aside>
  );
}

function formatTimestamp(value: string): string {
  const timestamp = new Date(value).getTime();
  if (!Number.isFinite(timestamp)) return "";
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (elapsedSeconds < 60) return "Just now";
  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) return `${elapsedMinutes}m ago`;
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) return `${elapsedHours}h ago`;
  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 7) return `${elapsedDays}d ago`;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    year: new Date(value).getFullYear() === new Date().getFullYear() ? undefined : "numeric",
  }).format(new Date(value));
}
