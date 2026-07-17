"""
LankaLawBot GraphRAG Hybrid Search Test.
Connects directly to Neo4j, retrieves Jina embeddings (jina-embeddings-v4),
executes hybrid search queries (Vector + Full-Text + Graph Traversal + Metadata Filters),
and fuses the results.
"""

import os
import time
import httpx
from neo4j import GraphDatabase

# ---------------------------------------------------------------------------
# Configuration & Connection Setup
# ---------------------------------------------------------------------------
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://0.tcp.in.ngrok.io:20123")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "lankalawbot2026")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
JINA_API_KEY = os.environ.get("JINA_API_KEY", "")

# Validation
if not JINA_API_KEY:
    raise ValueError(
        "Missing JINA_API_KEY environment variable. Please set it to proceed."
    )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------
def get_jina_embedding(text: str) -> list:
    """Fetches a 2048-dimensional query embedding from Jina AI."""
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    data = {
        "model": "jina-embeddings-v4",
        "input": [text],
        "task": "retrieval.query",
        "dimensions": 2048,
    }
    response = httpx.post(
        "https://api.jina.ai/v1/embeddings", json=data, headers=headers, timeout=30.0
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Jina API returned error {response.status_code}: {response.text}"
        )
    return response.json()["data"][0]["embedding"]


def test_hybrid_search(query: str, year_filter: int = None, limit: int = 3):
    """Executes Vector Search + FTS + Graph Traversal + Metadata filters, then prints results."""
    print(f"\n{'='*80}")
    print(f"🔎 RUNNING SEARCH FOR QUERY: '{query}'")
    if year_filter:
        print(f"📅 Filtered to Year: >= {year_filter}")
    print(f"{'='*80}")

    # Initialize Neo4j connection
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        # Get query embedding vector
        print("🤖 Generating Jina embedding vector...")
        query_embedding = get_jina_embedding(query)

        with driver.session(database=NEO4J_DATABASE) as session:
            # ---------------------------------------------------------------
            # 1. Vector Search Query (Dense Semantic Search)
            # ---------------------------------------------------------------
            vector_cypher = """
            CALL db.index.vector.queryNodes("chunk-embeddings", 15, $embedding)
            YIELD node AS chunk, score
            WHERE chunk.chunk_type IN ['child', 'section_summary']
              AND chunk.is_current = true
              AND ($year_filter IS NULL OR chunk.year >= $year_filter)
            RETURN chunk.chunk_id AS id, coalesce(chunk.title, chunk.case_name) AS doc, 
                   chunk.text AS text, score, chunk.breadcrumb AS path
            ORDER BY score DESC LIMIT $limit
            """
            print("\n🔵 Executing Vector Search...")
            v_res = session.run(
                vector_cypher,
                embedding=query_embedding,
                year_filter=year_filter,
                limit=limit,
            )
            v_chunks = []
            for r in v_res:
                v_chunks.append(r)
                print(f"   [{r['score']:.4f}] {r['doc']} > {r['path'] or 'General'}")

            # ---------------------------------------------------------------
            # 2. Full-Text Search Query (Lexical Keyword Search)
            # ---------------------------------------------------------------
            fts_cypher = """
            CALL db.index.fulltext.queryNodes("chunk-fulltext", $query_text)
            YIELD node AS chunk, score
            WHERE chunk.chunk_type IN ['child', 'section_summary']
              AND chunk.is_current = true
              AND ($year_filter IS NULL OR chunk.year >= $year_filter)
            RETURN chunk.chunk_id AS id, coalesce(chunk.title, chunk.case_name) AS doc, 
                   chunk.text AS text, score, chunk.breadcrumb AS path
            ORDER BY score DESC LIMIT $limit
            """
            print("\n🟢 Executing Full-Text Keyword Search...")
            f_res = session.run(
                fts_cypher, query_text=query, year_filter=year_filter, limit=limit
            )
            f_chunks = []
            for r in f_res:
                f_chunks.append(r)
                print(f"   [{r['score']:.4f}] {r['doc']} > {r['path'] or 'General'}")

            # Collect seed IDs for graph traversal
            seed_ids = list(set([r["id"] for r in v_chunks + f_chunks]))

            # ---------------------------------------------------------------
            # 3. Cypher Graph Traversal (Cross-node citations expansion)
            # ---------------------------------------------------------------
            if seed_ids:
                graph_cypher = """
                UNWIND $seed_ids AS seed_id
                MATCH (seed:Chunk {chunk_id: seed_id})
                
                // Expand to Section -> Act
                OPTIONAL MATCH (seed)<-[:HAS_CHUNK]-(s:Section)<-[:HAS_SECTION]-(a:Act)
                
                // Traverse Case Law citation relationships
                OPTIONAL MATCH (case:CaseLaw)-[:CITES_STATUTE|INTERPRETS]->(s)
                OPTIONAL MATCH (case)-[:HAS_CHUNK]->(case_c:Chunk)
                
                // Traverse Concept connections
                OPTIONAL MATCH (s)-[:RELATES_TO]->(concept:LegalConcept)<-[:RELATES_TO]-(other_s:Section)
                OPTIONAL MATCH (other_s)-[:HAS_CHUNK]->(concept_c:Chunk)
                
                WITH collect(DISTINCT case_c) + collect(DISTINCT concept_c) AS combined
                UNWIND combined AS chunk
                WITH DISTINCT chunk
                WHERE chunk IS NOT NULL 
                  AND chunk.chunk_type IN ['child', 'section_summary']
                  AND chunk.is_current = true
                RETURN coalesce(chunk.title, chunk.case_name) AS doc, chunk.breadcrumb AS path, chunk.text AS text
                LIMIT $limit
                """
                print(
                    "\n🟣 Executing Cypher Graph Traversal (expanding on citations & concepts)..."
                )
                g_res = session.run(graph_cypher, seed_ids=seed_ids, limit=limit)
                g_chunks = []
                for r in g_res:
                    g_chunks.append(r)
                    print(f"   [Traversed] {r['doc']} > {r['path'] or 'General'}")

            # ---------------------------------------------------------------
            # Print Context Snippets for evaluation
            # ---------------------------------------------------------------
            print("\n📝 TOP RETRIEVED TEXT PASSAGES:")
            all_hits = v_chunks[:2] + f_chunks[:1]
            if seed_ids:
                all_hits += g_chunks[:1]

            for idx, r in enumerate(all_hits, 1):
                clean_text = r["text"].replace("\n", " ")
                snippet = (
                    clean_text[:200] + "..." if len(clean_text) > 200 else clean_text
                )
                print(
                    f"  {idx}. [{r.get('doc')}] > {r.get('path') or 'General'}\n     \"{snippet}\"\n"
                )

    finally:
        driver.close()


# ---------------------------------------------------------------------------
# Test Query Definitions
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Test Query 1: Eppawala/Bulankulama Case Law query
    test_hybrid_search(
        query="Public Trust Doctrine and sovereignty of the people in Eppawala natural resources",
        limit=2,
    )

    # Test Query 2: Marriage and divorce statutory law query
    test_hybrid_search(
        query="Kandyan Marriage and Divorce Ordinance validity Christian minister solemnization",
        limit=2,
    )

    # Test Query 3: Fundamental Rights & equal protection constitutional query (filtered to post-2000)
    test_hybrid_search(
        query="Fundamental Rights violations under Article 12(1) equal protection",
        year_filter=2000,
        limit=2,
    )
