"use client";

import React, { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

import { CitationPill } from "@/components/CitationPill";
import type { SourceRef } from "@/lib/api";
import {
  buildSourcesById,
  citationIdsFromGroup,
  CITATION_RE,
} from "@/lib/sources";

export { CITATION_RE } from "@/lib/sources";

function renderCitations(
  text: string,
  sourcesById: Map<string, SourceRef>,
  onViewInSources?: (citationId: string) => void,
): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CITATION_RE)) {
    const start = match.index!;
    if (start > lastIndex) {
      parts.push(text.slice(lastIndex, start));
    }
    citationIdsFromGroup(match[0]).forEach((citationId, groupIndex) => {
      if (groupIndex > 0) parts.push(", ");
      parts.push(
        <CitationPill
          key={`${citationId}-${start}-${groupIndex}`}
          citationId={citationId}
          source={sourcesById.get(citationId)}
          onViewInSources={
            onViewInSources
              ? () => onViewInSources(citationId)
              : undefined
          }
        />,
      );
    });
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

function processChildren(
  children: React.ReactNode,
  sourcesById: Map<string, SourceRef>,
  onViewInSources?: (citationId: string) => void,
): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      return renderCitations(child, sourcesById, onViewInSources);
    }
    return child;
  });
}

function createMdComponents(
  sourcesById: Map<string, SourceRef>,
  onViewInSources?: (citationId: string) => void,
): Components {
  const process = (children: React.ReactNode) =>
    processChildren(children, sourcesById, onViewInSources);

  return {
    h1: ({ children }) => (
      <h1 className="text-xl font-bold text-app-strong mt-4 mb-2 border-b border-app-border/50 pb-1">
        {children}
      </h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-lg font-semibold text-app-primary mt-4 mb-2">
        {children}
      </h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-base font-semibold text-app-secondary mt-3 mb-1">
        {children}
      </h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-sm font-semibold text-app-tertiary mt-2 mb-1">
        {children}
      </h4>
    ),
    p: ({ children }) => (
      <p className="text-app-tertiary text-sm leading-relaxed mb-2">
        {process(children)}
      </p>
    ),
    strong: ({ children }) => (
      <strong className="text-app-primary font-semibold">
        {process(children)}
      </strong>
    ),
    em: ({ children }) => (
      <em className="text-app-tertiary italic">{process(children)}</em>
    ),
    ul: ({ children }) => (
      <ul className="list-disc list-inside text-app-tertiary text-sm space-y-1 mb-2 ml-2">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal list-inside text-app-tertiary text-sm space-y-1 mb-2 ml-2">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed">{process(children)}</li>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-3 border-app-accent/60 pl-3 my-2 text-app-muted text-sm italic">
        {children}
      </blockquote>
    ),
    code: ({ children, className }) => {
      const isBlock = className?.startsWith("language-");
      if (isBlock) {
        return (
          <code className="block bg-app-overlay/60 rounded-lg p-3 text-xs text-app-tertiary overflow-x-auto my-2 font-mono">
            {children}
          </code>
        );
      }
      return (
        <code className="bg-app-hover/50 text-app-accent px-1.5 py-0.5 rounded text-xs font-mono">
          {children}
        </code>
      );
    },
    pre: ({ children }) => <pre className="my-2">{children}</pre>,
    table: ({ children }) => (
      <div className="overflow-x-auto my-3 rounded-lg border border-app-border/50">
        <table className="w-full text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-app-elevated/60 text-app-secondary">{children}</thead>
    ),
    tbody: ({ children }) => <tbody>{children}</tbody>,
    tr: ({ children }) => (
      <tr className="border-b border-app-border/30">{children}</tr>
    ),
    th: ({ children }) => (
      <th className="px-3 py-2 text-left font-semibold text-xs">{children}</th>
    ),
    td: ({ children }) => (
      <td className="px-3 py-2 text-app-tertiary text-xs">{process(children)}</td>
    ),
    hr: () => <hr className="border-app-border/50 my-4" />,
    a: ({ children, href }) => (
      <a
        href={href}
        className="text-app-accent hover:text-app-accent-hover underline underline-offset-2"
        target="_blank"
        rel="noopener noreferrer"
      >
        {children}
      </a>
    ),
  };
}

interface MarkdownRendererProps {
  content: string;
  sources?: SourceRef[];
  onViewInSources?: (citationId: string) => void;
}

export function MarkdownRenderer({
  content,
  sources = [],
  onViewInSources,
}: MarkdownRendererProps) {
  const sourcesById = useMemo(() => buildSourcesById(sources), [sources]);

  const mdComponents = useMemo(
    () => createMdComponents(sourcesById, onViewInSources),
    [sourcesById, onViewInSources],
  );

  if (!content) return null;

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
