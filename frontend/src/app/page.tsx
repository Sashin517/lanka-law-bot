"use client";

import { useState } from "react";

export default function Home() {
  const [query, setQuery] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setAnswer("");

    try {
      // This is the bridge! It sends your question to the FastAPI server running on port 8000
      const response = await fetch("http://127.0.0.1:8000/api/search", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: query }),
      });

      const data = await response.json();
      setAnswer(data.answer || "No response received.");
    } catch (error) {
      console.error("Error fetching data:", error);
      setAnswer("⚠️ Error: Could not connect to the LankaLawBot backend. Is your FastAPI server running?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-slate-50 p-8 flex flex-col items-center font-sans">
      <div className="max-w-4xl w-full space-y-8 mt-12">
        
        {/* Header Section */}
        <div className="text-center space-y-4">
          <h1 className="text-5xl font-extrabold text-slate-900 tracking-tight">
            LankaLaw<span className="text-blue-600">Bot</span> ⚖️
          </h1>
          <p className="text-lg text-slate-600 max-w-2xl mx-auto">
            Your AI-powered legal assistant for Sri Lankan civil and commercial law. 
            Search through statutes, acts, and legal precedents instantly.
          </p>
        </div>

        {/* Search Bar Section */}
        <form onSubmit={handleSearch} className="flex flex-col sm:flex-row gap-4">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a legal question (e.g., What are the rules regarding tenancy termination?)"
            className="flex-1 p-5 rounded-xl border border-slate-300 shadow-sm text-slate-900 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-lg"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={loading}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-5 px-10 rounded-xl shadow-md transition-all disabled:bg-slate-400 disabled:cursor-not-allowed text-lg"
          >
            {loading ? "Searching..." : "Search"}
          </button>
        </form>

        {/* Results Section */}
        {answer && (
          <div className="bg-white p-8 rounded-2xl shadow-sm border border-slate-200 mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            <h2 className="text-xl font-bold text-slate-900 mb-4 border-b pb-2">AI Response & Sources</h2>
            <div className="prose prose-slate max-w-none text-slate-700 whitespace-pre-wrap leading-relaxed">
              {answer}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}