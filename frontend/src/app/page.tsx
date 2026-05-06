"use client";

import { useState } from "react";
import { Search, ChevronDown, ChevronUp, Plus, X, PenTool, CheckSquare, BarChart2, User } from "lucide-react";

export default function ResearchDashboard() {
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("acts");
  const [addedMaterials, setAddedMaterials] = useState<any[]>([]);
  const [hasSearched, setHasSearched] = useState(false); // Tracks if user hit search
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  
  // Filter States matching the exact UI
  const [filterSource, setFilterSource] = useState({ acts: true, caseLaws: true });
  const [filterDate, setFilterDate] = useState("all");
  const [openSections, setOpenSections] = useState({ source: true, date: true, topic: true, court: true, principle: false });

const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    
    setHasSearched(true);
    setIsLoading(true); // Start loading
    
    let start_year = null;
    if (filterDate === "last5") start_year = new Date().getFullYear() - 5;
    
    let doc_type = null;
    if (filterSource.acts && !filterSource.caseLaws) doc_type = "Act";
    if (!filterSource.acts && filterSource.caseLaws) doc_type = "Case Law";

    try {
      const response = await fetch("http://127.0.0.1:8000/api/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: searchQuery, doc_type, start_year }),
      });
      
      const data = await response.json();
      setSearchResults(data.results || []); // Save real data to state
    } catch (error) {
      console.error("Error fetching from backend:", error);
    } finally {
      setIsLoading(false); // Stop loading
    }
  };

  const toggleMaterial = (doc: any) => {
    if (addedMaterials.find(item => item.id === doc.id)) {
      setAddedMaterials(addedMaterials.filter(item => item.id !== doc.id));
    } else {
      setAddedMaterials([...addedMaterials, doc]);
    }
  };

  const toggleSection = (section: keyof typeof openSections) => {
    setOpenSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    // Main Background matching Figma's dark canvas
    <div className="min-h-screen flex flex-col bg-[#2A3241] font-sans">
      
      {/* NAVBAR */}
      <header className="bg-[#161B28] text-white flex items-center justify-between px-8 py-4 z-10 border-b border-slate-700/50">
        <div className="text-2xl font-serif tracking-wide text-white">
          LankaLawBot
        </div>
        <nav className="flex space-x-12">
          <button className="flex items-center space-x-2 text-[#D4AF37] border-b-2 border-[#D4AF37] pb-1">
            <Search size={18} /><span>Research</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <PenTool size={18} /><span>Draft</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <CheckSquare size={18} /><span>Verify</span>
          </button>
          <button className="flex items-center space-x-2 text-slate-400 hover:text-white transition">
            <BarChart2 size={18} /><span>Analyze</span>
          </button>
        </nav>
        <div className="bg-[#2A3241] p-2 rounded-full cursor-pointer hover:bg-slate-600 transition">
          <User size={20} className="text-slate-300" />
        </div>
      </header>

      {/* TOP SEARCH BAR */}
      <div className="bg-[#161B28] py-6 px-12 flex flex-col items-center shadow-sm">
        <form onSubmit={handleSearch} className="flex w-full max-w-4xl relative">
          <Search className="absolute left-6 top-1/2 transform -translate-y-1/2 text-slate-400" size={20} />
          <input 
            type="text" 
            placeholder="Ask legal question to get started..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-14 pr-4 py-3 rounded-l-full bg-white text-slate-900 focus:outline-none shadow-inner"
          />
          <button type="submit" className="bg-[#D4AF37] hover:bg-[#C5A030] text-[#161B28] font-bold px-10 py-3 rounded-r-full flex items-center space-x-2 transition">
            <Search size={18} /> <span>Search</span>
          </button>
        </form>
      </div>

        {hasSearched ? (
        <>
          <div className="px-12 py-4 text-slate-300 text-sm">
            Results for: <span className="text-white font-semibold">{searchQuery}</span>
          </div>
          <div className="flex flex-1 overflow-hidden px-12 pb-8 gap-6">
        
        {/* LEFT SIDEBAR: FILTERS */}
        <aside className="w-[280px] bg-[#161B28] rounded-xl text-white p-6 overflow-y-auto shadow-lg flex flex-col gap-6 custom-scrollbar">
          <h2 className="text-lg font-semibold mb-2">Filters</h2>

          {/* Source Type */}
          <div className="space-y-3">
            <div onClick={() => toggleSection('source')} className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm">
              <span>Source Type</span> {openSections.source ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.source && (
              <div className="space-y-3 pt-1 px-2 text-sm text-slate-300">
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input type="checkbox" checked={filterSource.acts} onChange={(e) => setFilterSource({...filterSource, acts: e.target.checked})} className="w-4 h-4 accent-[#D4AF37]" />
                  <span>Acts</span>
                </label>
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input type="checkbox" checked={filterSource.caseLaws} onChange={(e) => setFilterSource({...filterSource, caseLaws: e.target.checked})} className="w-4 h-4 accent-[#D4AF37]" />
                  <span>Case Laws</span>
                </label>
              </div>
            )}
          </div>

          {/* Date Range */}
          <div className="space-y-3">
            <div onClick={() => toggleSection('date')} className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm">
              <span>Date Range</span> {openSections.date ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.date && (
              <div className="space-y-3 pt-1 px-2 text-sm text-slate-300">
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input type="radio" name="date" checked={filterDate === "all"} onChange={() => setFilterDate("all")} className="w-4 h-4 accent-[#D4AF37]" />
                  <span>All Time</span>
                </label>
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input type="radio" name="date" checked={filterDate === "last5"} onChange={() => setFilterDate("last5")} className="w-4 h-4 accent-[#D4AF37]" />
                  <span>Last 5 Years</span>
                </label>
                <label className="flex items-center space-x-3 cursor-pointer hover:text-white">
                  <input type="radio" name="date" checked={filterDate === "custom"} onChange={() => setFilterDate("custom")} className="w-4 h-4 accent-[#D4AF37]" />
                  <span>Custom</span>
                </label>
              </div>
            )}
          </div>

          {/* Collapsed Placeholders */}
          {/* Topic / Legal Domain */}
          <div className="space-y-3">
            <div onClick={() => toggleSection('topic')} className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm">
              <span>Topic</span> {openSections.topic ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </div>
            {openSections.topic && (
              <div className="space-y-3 pt-1 px-2 text-sm text-slate-300">
                {['Contract & Commercial', 'Property & Land', 'Labour & Employment', 'Civil Procedure'].map(topic => (
                  <label key={topic} className="flex items-center space-x-3 cursor-pointer hover:text-white">
                    <input type="checkbox" className="w-4 h-4 accent-[#D4AF37]" />
                    <span>{topic}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* Court Level (Conditionally rendered: Hides if ONLY Acts are selected) */}
          {filterSource.caseLaws && (
            <div className="space-y-3">
              <div onClick={() => toggleSection('court')} className="bg-[#C5D0E6] text-[#161B28] p-2 rounded flex justify-between items-center cursor-pointer font-semibold text-sm">
                <span>Court level</span> {openSections.court ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
              {openSections.court && (
                <div className="space-y-3 pt-1 px-2 text-sm text-slate-300">
                  {['Supreme Court (SC)', 'Court of Appeal (COA)', 'Commercial High Court (CHC)', 'District Court (DC)'].map(court => (
                    <label key={court} className="flex items-center space-x-3 cursor-pointer hover:text-white">
                      <input type="checkbox" className="w-4 h-4 accent-[#D4AF37]" />
                      <span>{court}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}
        </aside>

        {/* MIDDLE: SEARCH RESULTS */}
        <main className="flex-1 flex flex-col min-w-0">
          {/* Tabs */}
          <div className="flex gap-4 mb-6">
            <button 
              onClick={() => setActiveTab("acts")}
              className={`flex-1 py-3 rounded-lg font-bold flex justify-between items-center px-6 transition ${activeTab === "acts" ? "bg-[#D4AF37] text-[#161B28]" : "bg-[#EAECEF] text-slate-600 hover:bg-slate-300"}`}
            >
              <span>Acts</span> <span className="bg-white/50 text-[#161B28] px-2 py-0.5 rounded-full text-xs">3</span>
            </button>
            <button 
              onClick={() => setActiveTab("case_laws")}
              className={`flex-1 py-3 rounded-lg font-bold flex justify-between items-center px-6 transition ${activeTab === "case_laws" ? "bg-[#D4AF37] text-[#161B28]" : "bg-[#EAECEF] text-slate-600 hover:bg-slate-300"}`}
            >
              <span>Case Laws</span> <span className="bg-[#161B28]/10 text-slate-600 px-2 py-0.5 rounded-full text-xs">4</span>
            </button>
          </div>

          {/* Results Grid */}
          <div className="grid grid-cols-2 gap-6 overflow-y-auto custom-scrollbar pb-4 pr-2">
            {isLoading ? (
              <div className="col-span-2 text-center text-slate-400 py-10">
                Analyzing Sri Lankan Law and retrieving precedents...
              </div>
            ) : searchResults.length === 0 ? (
              <div className="col-span-2 text-center text-slate-400 py-10">
                No relevant documents found for this query.
              </div>
            ) : (
              searchResults.map((result) => {
                const isAdded = addedMaterials.find(item => item.id === result.id);
                return (
                  <div key={result.id} className="bg-[#EAECEF] p-6 rounded-xl shadow-sm flex flex-col justify-between">
                    <div>
                      <h3 className="font-bold text-slate-900 font-serif text-lg leading-snug">{result.title}</h3>
                    <p className="font-bold text-slate-900 text-sm mb-4">{result.subtitle}</p>
                    <p className="text-slate-700 text-sm mb-6 leading-relaxed">{result.excerpt}</p>
                  </div>
                  <div className="flex justify-between items-center mt-auto">
                    <span className="text-xs font-semibold text-slate-500 bg-slate-200/80 border border-slate-300 px-3 py-1.5 rounded-md">
                      Relevance Score: {result.score}
                    </span>
                    <button 
                      onClick={() => toggleMaterial(result)}
                      className={`flex items-center space-x-1 px-4 py-2 rounded-md font-bold text-sm transition ${isAdded ? "bg-[#161B28] text-white" : "bg-[#5A6577] hover:bg-[#161B28] text-white"}`}
                    >
                      {isAdded ? <CheckSquare size={14} /> : <Plus size={14} />} 
                      <span>{isAdded ? "Added" : "Add"}</span>
                    </button>
                  </div>
                </div>
              )}))
            }
          </div>
        </main>

        {/* RIGHT SIDEBAR: ADDED MATERIALS */}
        <aside className="w-[300px] bg-[#161B28] rounded-xl text-white p-6 shadow-lg flex flex-col">
          <h2 className="text-lg font-semibold mb-6 pb-4 border-b border-slate-700">Added materials</h2>
          
          <div className="flex-1 overflow-y-auto space-y-3 custom-scrollbar">
            {addedMaterials.length === 0 ? (
              <p className="text-slate-400 text-sm italic">No materials added yet. Click "+ Add" on a document to save it here for drafting.</p>
            ) : (
              addedMaterials.map((item) => (
                <div key={item.id} className="flex justify-between items-start group">
                  <div>
                    <h4 className="text-sm font-sans text-slate-200 group-hover:text-white transition">{item.title}</h4>
                    <p className="text-xs text-slate-400 mt-0.5">{item.subtitle}</p>
                  </div>
                  <button onClick={() => toggleMaterial(item)} className="text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-600 rounded-full p-1 ml-2 transition">
                    <X size={14} />
                  </button>
                </div>
              ))
            )}
          </div>
      </aside>

          </div>
        </>
      ) : (
        <div className="flex flex-1 items-center justify-center text-slate-400 italic">
          Enter a legal query in the search bar to begin your research.
        </div>
      )}
      
    </div>
  );
}