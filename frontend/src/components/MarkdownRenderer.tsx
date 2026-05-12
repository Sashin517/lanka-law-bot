"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

/* ── Citation pill regex: matches [LAW-1], [DOC-2], etc. ── */
const CITATION_RE = /\[(?:LAW|DOC)-\d+\]/g;

/**
 * Splits text into plain segments and citation pill spans.
 */
function renderCitations(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;

  for (const match of text.matchAll(CITATION_RE)) {
    const start = match.index!;
    if (start > lastIndex) {
      parts.push(text.slice(lastIndex, start));
    }
    const isDoc = match[0].startsWith("[DOC");
    parts.push(
      <span
        key={`${match[0]}-${start}`}
        className={`inline-block text-[10px] font-bold px-1.5 py-0.5 rounded mx-0.5 align-middle ${
          isDoc
            ? "bg-purple-400/20 text-purple-400"
            : "bg-[#D4AF37]/20 text-[#D4AF37]"
        }`}
      >
        {match[0]}
      </span>
    );
    lastIndex = start + match[0].length;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts;
}

/* ── Markdown component overrides for dark theme ── */
const mdComponents: Components = {
  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-white mt-4 mb-2 border-b border-slate-700/50 pb-1">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-semibold text-slate-100 mt-4 mb-2">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-semibold text-slate-200 mt-3 mb-1">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-sm font-semibold text-slate-300 mt-2 mb-1">
      {children}
    </h4>
  ),
  p: ({ children }) => {
    // Process text children to highlight citation anchors
    const processed = React.Children.map(children, (child) => {
      if (typeof child === "string") {
        return renderCitations(child);
      }
      return child;
    });
    return (
      <p className="text-slate-300 text-sm leading-relaxed mb-2">
        {processed}
      </p>
    );
  },
  strong: ({ children }) => (
    <strong className="text-slate-100 font-semibold">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="text-slate-300 italic">{children}</em>
  ),
  ul: ({ children }) => (
    <ul className="list-disc list-inside text-slate-300 text-sm space-y-1 mb-2 ml-2">
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol className="list-decimal list-inside text-slate-300 text-sm space-y-1 mb-2 ml-2">
      {children}
    </ol>
  ),
  li: ({ children }) => {
    const processed = React.Children.map(children, (child) => {
      if (typeof child === "string") {
        return renderCitations(child);
      }
      return child;
    });
    return <li className="leading-relaxed">{processed}</li>;
  },
  blockquote: ({ children }) => (
    <blockquote className="border-l-3 border-[#D4AF37]/60 pl-3 my-2 text-slate-400 text-sm italic">
      {children}
    </blockquote>
  ),
  code: ({ children, className }) => {
    // Inline code vs code blocks
    const isBlock = className?.startsWith("language-");
    if (isBlock) {
      return (
        <code className="block bg-slate-900/60 rounded-lg p-3 text-xs text-slate-300 overflow-x-auto my-2 font-mono">
          {children}
        </code>
      );
    }
    return (
      <code className="bg-slate-700/50 text-[#D4AF37] px-1.5 py-0.5 rounded text-xs font-mono">
        {children}
      </code>
    );
  },
  pre: ({ children }) => <pre className="my-2">{children}</pre>,
  table: ({ children }) => (
    <div className="overflow-x-auto my-3 rounded-lg border border-slate-700/50">
      <table className="w-full text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-slate-800/60 text-slate-200">{children}</thead>
  ),
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => (
    <tr className="border-b border-slate-700/30">{children}</tr>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-semibold text-xs">{children}</th>
  ),
  td: ({ children }) => {
    const processed = React.Children.map(children, (child) => {
      if (typeof child === "string") {
        return renderCitations(child);
      }
      return child;
    });
    return (
      <td className="px-3 py-2 text-slate-300 text-xs">{processed}</td>
    );
  },
  hr: () => <hr className="border-slate-700/50 my-4" />,
  a: ({ children, href }) => (
    <a
      href={href}
      className="text-[#D4AF37] hover:text-[#E5C040] underline underline-offset-2"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),
};

/* ── Main component ── */

interface MarkdownRendererProps {
  content: string;
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  if (!content) return null;

  return (
    <div className="markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
