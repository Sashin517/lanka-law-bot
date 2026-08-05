"""Shared Cypher for the fallback legal-corpus graph contract."""

AMENDMENT_RELATIONSHIP_TYPES = ["AMENDS", "REPEALS"]
CASE_RELATIONSHIP_TYPES = ["CITES_STATUTE", "INTERPRETS", "CITES_CASE"]
CONCEPT_RELATIONSHIP_TYPES = ["RELATES_TO", "ESTABLISHES_PRINCIPLE"]

CHUNK_PROJECTION = """chunk {
    .chunk_id, .text, .chunk_type, .parent_chunk_id, .text_hash,
    .year, .title, .source_type, .source_filename, .breadcrumb,
    .is_current, .section_id, .act_id
}"""

GRAPH_TRAVERSAL_QUERY = f"""
UNWIND $seed_chunk_ids AS seed_id
MATCH (seed:Chunk {{chunk_id: seed_id}})
MATCH (seed_root)
WHERE (seed_root:Act AND seed_root.act_id = seed.act_id) 
   OR (seed_root:CaseLaw AND seed_root.case_id = seed.act_id)
CALL {{
    // Citations to statutes (sections)
    WITH seed_root
    MATCH (seed_root)-[rel:CITES_STATUTE|INTERPRETS]->(s:Section)-[:HAS_CHUNK]->(chunk:Chunk)
    RETURN chunk, 0.92 AS path_score, type(rel) AS path_type
    UNION
    // Citations to cases
    WITH seed_root
    MATCH (seed_root)-[rel:CITES_CASE]->(target:CaseLaw)-[:HAS_CHUNK]->(chunk:Chunk)
    RETURN chunk, 0.90 AS path_score, type(rel) AS path_type
    UNION
    // Works citing this work (either its section or case)
    WITH seed, seed_root
    MATCH (other_root)-[rel:CITES_STATUTE|INTERPRETS]->(s:Section)
    WHERE s.section_id = seed.section_id OR s.act_id = seed_root.act_id
    OPTIONAL MATCH (other_root:Act)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(chunk_a:Chunk)
    OPTIONAL MATCH (other_root:CaseLaw)-[:HAS_CHUNK]->(chunk_c:Chunk)
    WITH coalesce(chunk_a, chunk_c) AS chunk, rel
    WHERE chunk IS NOT NULL
    RETURN chunk, 0.91 AS path_score, type(rel) AS path_type
    UNION
    // Works citing this case
    WITH seed_root
    MATCH (other_root)-[rel:CITES_CASE]->(seed_root)
    OPTIONAL MATCH (other_root:Act)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(chunk_a:Chunk)
    OPTIONAL MATCH (other_root:CaseLaw)-[:HAS_CHUNK]->(chunk_c:Chunk)
    WITH coalesce(chunk_a, chunk_c) AS chunk, rel
    WHERE chunk IS NOT NULL
    RETURN chunk, 0.91 AS path_score, type(rel) AS path_type
    UNION
    // Shared concepts
    WITH seed_root
    MATCH (seed_root)-[:RELATES_TO|ESTABLISHES_PRINCIPLE]->(concept:LegalConcept)<-[:RELATES_TO|ESTABLISHES_PRINCIPLE]-(other_root)
    WHERE other_root <> seed_root
    OPTIONAL MATCH (other_root:Act)-[:HAS_SECTION]->(:Section)-[:HAS_CHUNK]->(chunk_a:Chunk)
    OPTIONAL MATCH (other_root:CaseLaw)-[:HAS_CHUNK]->(chunk_c:Chunk)
    WITH coalesce(chunk_a, chunk_c) AS chunk
    WHERE chunk IS NOT NULL
    RETURN chunk, 0.76 AS path_score, 'shared_concept' AS path_type
}}
WITH chunk, path_score, path_type
WHERE chunk.chunk_type = 'child'
  AND NOT chunk.chunk_id IN $seed_chunk_ids
  AND (
      ($as_of IS NULL AND chunk.is_current = true)
      OR
      ($as_of IS NOT NULL AND chunk.is_current = true)
  )
WITH chunk, max(path_score) AS score, collect(DISTINCT path_type) AS graph_paths
RETURN {CHUNK_PROJECTION} AS chunk, score, graph_paths
ORDER BY score DESC, chunk.chunk_id
LIMIT $limit
"""
