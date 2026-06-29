import { create } from "zustand";
import { sendLegalQuery } from "@/lib/api";

export interface DraftSegment {
  id: string;
  text: string;
  sourceId: string | null;
  rejected: boolean;
}

interface DraftStore {
  question: string;
  segments: DraftSegment[];
  sources: any[];
  isLoading: boolean;
  error: string | null;
  startDraft: (question: string, documentIds: string[]) => Promise<void>;
  rejectSegment: (id: string) => void;
}

export const useDraftStore = create<DraftStore>((set) => ({
  question: "",
  segments: [],
  sources: [],
  isLoading: false,
  error: null,

  startDraft: async (question, documentIds) => {
    set({ isLoading: true, question, segments: [], sources: [], error: null });
    
    try {
      const data = await sendLegalQuery({
        question,
        mode: "drafting",
        matter_id: null,
        document_ids: documentIds,
      });

      // Parse the backend markdown into segments
      const text = data.markdown_content || "";
      const parts = text.split(/(\[(?:LAW|DOC)-\d+\])/g);
      
      let lastSourceId: string | null = null;
      const parsedSegments: DraftSegment[] = parts.map((part, i) => {
        const anchorMatch = part.match(/^\[(LAW|DOC)-(\d+)\]$/);
        if (anchorMatch) {
          lastSourceId = part;
          return null;
        }
        const seg: DraftSegment = {
          id: `seg-${i}`,
          text: part,
          sourceId: lastSourceId,
          rejected: false,
        };
        lastSourceId = null;
        return seg;
      }).filter(Boolean) as DraftSegment[];

      set({ segments: parsedSegments, sources: data.sources || [], isLoading: false });
    } catch (error) {
      set({ error: "Failed to generate draft.", isLoading: false });
    }
  },

  rejectSegment: (id) => 
    set((state) => ({
      segments: state.segments.map((s) => 
        s.id === id ? { ...s, rejected: true } : s
      )
    })),
}));