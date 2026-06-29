"use client";

/**
 * LankaLawBot — Draft Page
 * Route: /draft  (or shown when mode === "drafting" after submission)
 *
 * Layout:
 *   Top nav bar  (shared header — imported from layout)
 *   Sub-header   "Still Drafting…" status + Go Back / Review buttons
 *   Two-panel body
 *     LEFT  — AI Generated Draft   (highlighted spans, reject popover)
 *     RIGHT — Original Source Documents (mirrored doc + source list)
 */

import { useDraftStore } from "@/store/draftStore";
import { useRouter } from "next/navigation";

import { useState, useRef, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SourceDoc {
  id: string;
  title: string;           // e.g. "Civil Procedure Code"
  subtitle: string;        // e.g. "No. 2 of 1889, Section 18"
  status: "accepted" | "rejected";
  content: string;         // excerpt shown in right panel when selected
}

interface DraftSegment {
  id: string;
  text: string;
  sourceId: string | null; // null = plain text, non-null = cites a source
  rejected: boolean;
}

interface PopoverState {
  visible: boolean;
  segmentId: string | null;
  x: number;
  y: number;
}

// ─── Mock data (replace with real API response) ───────────────────────────────

const MOCK_SOURCES: SourceDoc[] = [
  {
    id: "src-1",
    title: "Civil Procedure Code",
    subtitle: "No. 2 of 1889, Section 18",
    status: "accepted",
    content:
      "Section 18 of the Civil Procedure Code provides that every suit shall be instituted in the Court of the lowest grade competent to try it. The provisions herein govern jurisdiction, venue, and proper forum selection for civil matters arising within the Democratic Socialist Republic of Sri Lanka.",
  },
  {
    id: "src-2",
    title: "Civil Procedure Code",
    subtitle: "No. 2 of 1889, Section 18",
    status: "accepted",
    content:
      "The standard of proof in civil proceedings is based on the balance of probabilities. Section 18 further clarifies that the burden of establishing facts lies with the party asserting them.",
  },
  {
    id: "src-3",
    title: "Civil Procedure Code",
    subtitle: "No. 2 of 1889, Section 18",
    status: "accepted",
    content:
      "Concerning procedural compliance, Section 18 mandates that pleadings be filed within the prescribed limitation period and conform to the prescribed format under Schedule I.",
  },
  {
    id: "src-4",
    title: "Civil Procedure Code",
    subtitle: "No. 2 of 1889, Section 18",
    status: "rejected",
    content:
      "REJECTED SOURCE: This provision was superseded by the Civil Procedure (Amendment) Act No. 14 of 1997 and is no longer operative in current proceedings.",
  },
  {
    id: "src-5",
    title: "Civil Procedure Code",
    subtitle: "No. 2 of 1889, Section 18",
    status: "rejected",
    content:
      "REJECTED SOURCE: The cited section does not directly apply to contract disputes; refer instead to the Sale of Goods Ordinance.",
  },
];

const MOCK_SEGMENTS: DraftSegment[] = [
  {
    id: "seg-1",
    text: "Draft Opinion regarding Contract Breach\n\nSubject: Opinion Regarding Liability for Contract Breach — [Client Name] v. [Opposing Party Name].\nDear [Client Name],\n\n",
    sourceId: null,
    rejected: false,
  },
  {
    id: "seg-2",
    text: "We have analyzed the facts surrounding the alleged breach of contract by [Opposing Party Name] concerning the supply agreement dated [Date]. Based on the provisions of the Civil Law Act, No. 56 of 2023 and relevant case law, we provide the following legal opinion…\n\n",
    sourceId: "src-1",
    rejected: false,
  },
  {
    id: "seg-3",
    text: "We have analyzed the fact alleged forl comampets at breach of contract by [Opposing Party Name] concerning the supply agreement dated and factos in the agrement to our oritment/voporary analysis of contract of the atgremenrtability to proverafe forms, an appiredgreaum of contract. Innther: contract the supply agreement,\n",
    sourceId: null,
    rejected: false,
  },
  {
    id: "seg-4",
    text: "eliminated ahead of recomtion und sranned out eptain / unforeseeability and conflict of the priovision task and must be atoirianzed in law, to provide the following legal opinion.",
    sourceId: "src-2",
    rejected: false,
  },
  {
    id: "seg-5",
    text: "\n\nThe facts are tn marksened the process in the complieys breach as is top elled by [Opposing Party Name] concerning the supply agreement. flind the principle of unforeseeeability its assurive reminnoian. I have preventonatex the analysis of Silva v. 2023 and motionate case-law, regenerate section: Sonsibility changes aircept tone-/ fire admance propvarite and contfact, the amel agreement. and/or concerning, the supply agreement dated arms. Based on the provision oil alillty amount, the sugenerate ansounment affeces in regarding the connage of the standard.\nHowever, the analyzed clamms rtile mot top reacurers are processed by [Opposing Party Name] are with the agreement and the fast of the desorts and periority of convenndure senses. The relevant section in paragraph 3 has been.\n",
    sourceId: "src-3",
    rejected: false,
  },
  {
    id: "seg-6",
    text: "eliminated ahead of recomtion und sranned out eptain / unforeseeability and conflict of the priovision task and must be atoirianzed in law, to provide the following legal opinion.",
    sourceId: "src-2",
    rejected: false,
  },
];

// ─── Sub-components ───────────────────────────────────────────────────────────

/** Toolbar shared by both panels */
function PanelToolbar({
  page,
  totalPages,
}: {
  page: number;
  totalPages: number;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "8px 12px",
        borderBottom: "1px solid rgba(88,100,139,0.25)",
        background: "rgba(11,25,52,0.4)",
        flexShrink: 0,
      }}
    >
      {/* Sidebar toggle */}
      <button style={toolbarBtnStyle} aria-label="Toggle sidebar">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <rect x="1" y="1" width="5" height="14" rx="1" stroke="currentColor" strokeWidth="1.2" />
          <rect x="8" y="1" width="7" height="14" rx="1" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>
      <button style={toolbarBtnStyle} aria-label="Zoom out">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.2" />
          <line x1="5" y1="7" x2="9" y2="7" stroke="currentColor" strokeWidth="1.2" />
          <line x1="10.5" y1="10.5" x2="14" y2="14" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>
      <button style={toolbarBtnStyle} aria-label="Zoom in">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.2" />
          <line x1="5" y1="7" x2="9" y2="7" stroke="currentColor" strokeWidth="1.2" />
          <line x1="7" y1="5" x2="7" y2="9" stroke="currentColor" strokeWidth="1.2" />
          <line x1="10.5" y1="10.5" x2="14" y2="14" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Pagination */}
      <button style={toolbarBtnStyle} aria-label="Previous page">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M9 11L5 7l4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </button>
      <span
        style={{
          fontSize: 12,
          color: "rgba(255,255,255,0.5)",
          border: "1px solid rgba(88,100,139,0.35)",
          borderRadius: 4,
          padding: "2px 8px",
          minWidth: 28,
          textAlign: "center",
        }}
      >
        {page}
      </span>
      <button style={toolbarBtnStyle} aria-label="Next page">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M5 3l4 4-4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </button>

      <div style={{ width: 1, height: 16, background: "rgba(88,100,139,0.3)" }} />

      {/* Expand & Download */}
      <button style={toolbarBtnStyle} aria-label="Expand">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M1 1h5M1 1v5M15 1h-5M15 1v5M1 15h5M1 15v-5M15 15h-5M15 15v-5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </button>
      <button style={toolbarBtnStyle} aria-label="Download">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M8 2v8M5 7l3 3 3-3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
          <path d="M2 12v2h12v-2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </button>
    </div>
  );
}

const toolbarBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  cursor: "pointer",
  color: "rgba(255,255,255,0.45)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: 4,
  borderRadius: 4,
  transition: "color 0.15s",
};

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DraftPage() {
  const router = useRouter();
  const { segments, sources, isLoading, rejectSegment } = useDraftStore();
  
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [popover, setPopover] = useState<PopoverState>({ visible: false, segmentId: null, x: 0, y: 0 });
  const leftPanelRef = useRef<HTMLDivElement>(null);

  // Clicking a cited segment: highlight source + show popover
  const handleSegmentClick = useCallback(
    (e: React.MouseEvent, segment: DraftSegment) => {
      if (!segment.sourceId) return;
      setSelectedSourceId(segment.sourceId);

      const rect = (e.target as HTMLElement).getBoundingClientRect();
      const panelRect = leftPanelRef.current?.getBoundingClientRect();
      setPopover({
        visible: true,
        segmentId: segment.id,
        x: rect.left - (panelRect?.left ?? 0),
        y: rect.bottom - (panelRect?.top ?? 0) + 4,
      });
    },
    []
  );

  const closePopover = () =>
    setPopover({ visible: false, segmentId: null, x: 0, y: 0 });

  const handleReject = () => {
    if (!popover.segmentId) return;
    rejectSegment(popover.segmentId);
    closePopover();
  };

  const activeSource = selectedSourceId
    ? MOCK_SOURCES.find((s) => s.id === selectedSourceId)
    : null;

  // ── Styles ─────────────────────────────────────────────────────────────────

  const pageStyle: React.CSSProperties = {
    minHeight: "100vh",
    background: "#1D2530",
    color: "#e2e8f0",
    fontFamily: "var(--font-lato, sans-serif)",
    display: "flex",
    flexDirection: "column",
  };

  const navStyle: React.CSSProperties = {
    height: 56,
    background: "#0B1934",
    borderBottom: "1px solid rgba(88,100,139,0.3)",
    display: "flex",
    alignItems: "center",
    padding: "0 24px",
    gap: 8,
    flexShrink: 0,
  };

  const navTabStyle = (active: boolean): React.CSSProperties => ({
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "6px 16px",
    borderRadius: 6,
    fontSize: 14,
    fontWeight: active ? 500 : 400,
    color: active ? "#D6B05D" : "rgba(255,255,255,0.45)",
    borderBottom: active ? "2px solid #D6B05D" : "2px solid transparent",
    background: "none",
    border: "none",
    cursor: "pointer",
    transition: "color 0.15s",
  });

  const subHeaderStyle: React.CSSProperties = {
    height: 52,
    background: "#0B1934",
    borderBottom: "1px solid rgba(88,100,139,0.2)",
    display: "flex",
    alignItems: "center",
    padding: "0 24px",
    gap: 12,
    flexShrink: 0,
  };

  const bodyStyle: React.CSSProperties = {
    flex: 1,
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 16,
    padding: "16px 16px 16px",
    overflow: "hidden",
    minHeight: 0,
  };

  const panelStyle: React.CSSProperties = {
    background: "rgba(11,25,52,0.5)",
    border: "1px solid rgba(88,100,139,0.25)",
    borderRadius: 8,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    minHeight: 0,
  };

  const panelHeaderStyle: React.CSSProperties = {
    padding: "10px 16px",
    fontSize: 13,
    fontWeight: 500,
    color: "rgba(255,255,255,0.6)",
    letterSpacing: "0.04em",
    borderBottom: "1px solid rgba(88,100,139,0.2)",
    background: "rgba(11,25,52,0.6)",
    flexShrink: 0,
  };

  const docBodyStyle: React.CSSProperties = {
    flex: 1,
    overflow: "auto",
    padding: "24px 28px",
    fontSize: 13.5,
    lineHeight: 1.75,
    color: "rgba(255,255,255,0.85)",
    position: "relative",
    scrollbarWidth: "thin",
    scrollbarColor: "rgba(88,100,139,0.3) transparent",
  };

  return (
    <div style={pageStyle} onClick={popover.visible ? closePopover : undefined}>
      {/* ── Top Navigation ── */}
      <nav style={navStyle}>
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginRight: 32 }}>
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="13" stroke="#D6B05D" strokeWidth="1.5" />
            <path d="M7 10h14M7 14h10M7 18h12" stroke="#D6B05D" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span
            style={{
              fontFamily: "var(--font-playfair, serif)",
              fontSize: 17,
              fontWeight: 600,
              color: "#fff",
              letterSpacing: "0.01em",
            }}
          >
            LankaLawBot
          </span>
        </div>

        {/* Nav tabs */}
        <div style={{ display: "flex", gap: 4, flex: 1, justifyContent: "center" }}>
          {[
            { label: "Research", icon: "🔍" },
            { label: "Draft", icon: "📋" },
            { label: "Verify", icon: "✓" },
            { label: "Ready", icon: "🤝" },
          ].map((tab) => (
            <button key={tab.label} style={navTabStyle(tab.label === "Draft")}>
              <span style={{ fontSize: 14 }}>{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>

        {/* Avatar */}
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: "50%",
            background: "rgba(88,100,139,0.4)",
            border: "1px solid rgba(88,100,139,0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="7" r="3.5" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" />
            <path d="M3 16c0-3.314 2.686-5 6-5s6 1.686 6 5" stroke="rgba(255,255,255,0.5)" strokeWidth="1.2" strokeLinecap="round" />
          </svg>
        </div>
      </nav>

      {/* ── Sub-header ── */}
      <div style={subHeaderStyle}>
        {/* Drafting status indicator */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
          {isLoading ? (
            <>
              <span style={{ 
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "#D6B05D",
                boxShadow: "0 0 6px #D6B05D88",
                animation: "pulse 2s infinite",
                flexShrink: 0,
               }} />
              <span style={{ fontSize: 13.5, color: "rgba(255,255,255,0.55)" }}>Still Drafting…</span>
            </>
          ) : (
            <span style={{ fontSize: 13.5, color: "#D6B05D" }}>Draft Ready</span>
          )}
        </div>

        {/* Action buttons */}
        <button
          onClick={() => router.push("/")}

          style={{
            padding: "7px 18px",
            borderRadius: 7,
            border: "1px solid rgba(88,100,139,0.45)",
            background: "transparent",
            color: "rgba(255,255,255,0.7)",
            fontSize: 13.5,
            fontWeight: 500,
            cursor: "pointer",
            transition: "background 0.15s, border-color 0.15s",
          }}
          onMouseEnter={(e) =>
            ((e.target as HTMLElement).style.background = "rgba(88,100,139,0.2)")
          }
          onMouseLeave={(e) =>
            ((e.target as HTMLElement).style.background = "transparent")
          }
        >
          Go back
        </button>
        <button
          style={{
            padding: "7px 20px",
            borderRadius: 7,
            border: "none",
            background: "#D6B05D",
            color: "#0B1934",
            fontSize: 13.5,
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 6,
            transition: "opacity 0.15s",
          }}
          onMouseEnter={(e) =>
            ((e.target as HTMLElement).style.opacity = "0.88")
          }
          onMouseLeave={(e) =>
            ((e.target as HTMLElement).style.opacity = "1")
          }
        >
          Review
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M3 7h8M8 4l3 3-3 3" stroke="#0B1934" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* ── Two-panel body ── */}
      <div style={bodyStyle}>
        {/* ═══ LEFT PANEL — AI Generated Draft ═══ */}
        <div style={panelStyle}>
          <div style={panelHeaderStyle}>Ai Generated Draft</div>
          <PanelToolbar page={1} totalPages={1} />

          <div style={docBodyStyle} ref={leftPanelRef}>
            {segments.map((seg) => {
              const isCited = !!seg.sourceId;
              const isSelected =
                isCited && seg.sourceId === selectedSourceId;
              const isRejected = seg.rejected;

              let bg = "transparent";
              if (isRejected) bg = "rgba(214,176,93,0.12)";
              else if (isSelected) bg = "rgba(214,176,93,0.22)";
              else if (isCited) bg = "rgba(88,148,214,0.15)";

              return (
                <span
                  key={seg.id}
                  style={{
                    background: bg,
                    borderRadius: isCited ? 3 : 0,
                    cursor: isCited && !isRejected ? "pointer" : "default",
                    textDecoration: isRejected ? "line-through" : "none",
                    color: isRejected ? "rgba(255,255,255,0.35)" : "inherit",
                    transition: "background 0.15s",
                    whiteSpace: "pre-wrap",
                    display: "inline",
                    position: "relative",
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (!isRejected) handleSegmentClick(e, seg);
                  }}
                >
                  {seg.text}
                </span>
              );
            })}

            {/* ── Reject / Cancel popover ── */}
            {popover.visible && (
              <div
                style={{
                  position: "absolute",
                  left: Math.min(popover.x, 320),
                  top: popover.y,
                  zIndex: 50,
                  background: "#0B1934",
                  border: "1px solid rgba(88,100,139,0.45)",
                  borderRadius: 8,
                  boxShadow: "0 8px 24px rgba(0,0,0,0.45)",
                  padding: "10px 12px",
                  display: "flex",
                  gap: 8,
                  alignItems: "center",
                  minWidth: 180,
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <span
                  style={{
                    fontSize: 12,
                    color: "rgba(255,255,255,0.5)",
                    marginRight: 4,
                  }}
                >
                  Citation:
                </span>
                <button
                  onClick={handleReject}
                  style={{
                    flex: 1,
                    padding: "5px 12px",
                    borderRadius: 5,
                    border: "1px solid rgba(214,80,80,0.45)",
                    background: "rgba(214,80,80,0.1)",
                    color: "#f87171",
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                >
                  Reject
                </button>
                <button
                  onClick={closePopover}
                  style={{
                    flex: 1,
                    padding: "5px 12px",
                    borderRadius: 5,
                    border: "1px solid rgba(88,100,139,0.45)",
                    background: "transparent",
                    color: "rgba(255,255,255,0.6)",
                    fontSize: 12.5,
                    fontWeight: 500,
                    cursor: "pointer",
                    transition: "background 0.15s",
                  }}
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>

        {/* ═══ RIGHT PANEL — Original Source Documents ═══ */}
        <div style={{ ...panelStyle, display: "flex", flexDirection: "column", gap: 0 }}>
          <div style={panelHeaderStyle}>Original Source Documents</div>

          {/* Mirrored document view (top ~55% of right panel) */}
          <div
            style={{
              flex: "0 0 auto",
              maxHeight: "45%",
              borderBottom: "1px solid rgba(88,100,139,0.2)",
              overflow: "auto",
              scrollbarWidth: "thin",
              scrollbarColor: "rgba(88,100,139,0.3) transparent",
            }}
          >
            <PanelToolbar page={1} totalPages={1} />
            <div style={{ ...docBodyStyle, flex: "none" }}>
              {activeSource ? (
                <>
                  <p
                    style={{
                      fontWeight: 600,
                      fontSize: 15,
                      marginBottom: 12,
                      color: "#fff",
                    }}
                  >
                    Draft Opinion regarding Contract Breach
                  </p>
                  <p style={{ marginBottom: 10 }}>
                    Subject: Opinion Regarding Liability for Contract Breach
                  </p>
                  {/* Yellow-highlighted excerpt */}
                  <span
                    style={{
                      background: "rgba(214,176,93,0.28)",
                      borderRadius: 3,
                      padding: "0 2px",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {activeSource.content}
                  </span>
                </>
              ) : (
                <p style={{ color: "rgba(255,255,255,0.35)", fontStyle: "italic" }}>
                  Click any highlighted passage in the draft to preview its source here.
                </p>
              )}
            </div>
          </div>

          {/* Source list (bottom ~45% of right panel) */}
          <div
            style={{
              flex: 1,
              overflow: "auto",
              padding: "12px 12px 16px",
              scrollbarWidth: "thin",
              scrollbarColor: "rgba(88,100,139,0.3) transparent",
              display: "flex",
              flexDirection: "column",
              gap: 0,
            }}
          >
            {/* Accepted sources */}
            {MOCK_SOURCES.filter((s) => s.status === "accepted").map((src) => (
              <SourceRow
                key={src.id}
                source={src}
                isSelected={src.id === selectedSourceId}
                onSelect={() =>
                  setSelectedSourceId(
                    src.id === selectedSourceId ? null : src.id
                  )
                }
              />
            ))}

            {/* Rejected divider */}
            {MOCK_SOURCES.some((s) => s.status === "rejected") && (
              <div
                style={{
                  padding: "10px 4px 6px",
                  fontSize: 11.5,
                  fontWeight: 600,
                  color: "rgba(255,255,255,0.35)",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                }}
              >
                Rejected
              </div>
            )}

            {MOCK_SOURCES.filter((s) => s.status === "rejected").map((src) => (
              <SourceRow
                key={src.id}
                source={src}
                isSelected={src.id === selectedSourceId}
                onSelect={() =>
                  setSelectedSourceId(
                    src.id === selectedSourceId ? null : src.id
                  )
                }
                dimmed
              />
            ))}
          </div>
        </div>
      </div>

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}

// ─── Source row component ─────────────────────────────────────────────────────

function SourceRow({
  source,
  isSelected,
  onSelect,
  dimmed = false,
}: {
  source: SourceDoc;
  isSelected: boolean;
  onSelect: () => void;
  dimmed?: boolean;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 12px",
        marginBottom: 6,
        borderRadius: 7,
        border: isSelected
          ? "1px solid rgba(214,176,93,0.5)"
          : "1px solid rgba(88,100,139,0.22)",
        background: isSelected
          ? "rgba(214,176,93,0.08)"
          : "rgba(11,25,52,0.4)",
        cursor: "pointer",
        opacity: dimmed ? 0.45 : 1,
        transition: "border-color 0.15s, background 0.15s",
      }}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
    >
      <div>
        <p
          style={{
            margin: 0,
            fontSize: 13,
            fontWeight: 500,
            color: dimmed ? "rgba(255,255,255,0.4)" : "rgba(255,255,255,0.85)",
          }}
        >
          {source.title}
        </p>
        <p
          style={{
            margin: "2px 0 0",
            fontSize: 11.5,
            color: dimmed ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.4)",
          }}
        >
          {source.subtitle}
        </p>
      </div>
      <button
        style={{
          flexShrink: 0,
          padding: "4px 14px",
          borderRadius: 5,
          border: "1px solid rgba(88,100,139,0.4)",
          background: "transparent",
          color: "rgba(255,255,255,0.55)",
          fontSize: 12,
          cursor: "pointer",
          transition: "border-color 0.15s, color 0.15s",
        }}
        onClick={(e) => {
          e.stopPropagation();
          onSelect();
        }}
      >
        View
      </button>
    </div>
  );
}