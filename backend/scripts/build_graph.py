import os
import json
import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_neo4j import Neo4jGraph
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Data Models for Extraction ---

class Node(BaseModel):
    id: str = Field(..., description="Unique identifier for the entity (e.g., Act name, Case name, Person, Organization).")
    label: str = Field(..., description="Type of entity (e.g., 'Act', 'Case', 'Organization', 'Person', 'Concept').")
    properties: dict = Field(default_factory=dict, description="Additional attributes (e.g., year, summary).")

class Relationship(BaseModel):
    source_id: str = Field(..., description="ID of the source node.")
    target_id: str = Field(..., description="ID of the target node.")
    type: str = Field(..., description="Type of relationship (e.g., 'AMENDS', 'CITES', 'REPEALS', 'APPLIES_TO', 'INVOLVES').")
    properties: dict = Field(default_factory=dict, description="Additional attributes (e.g., section, context).")

class GraphExtraction(BaseModel):
    nodes: List[Node] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)

# --- Graph Builder Logic ---

def build_graph():
    # Initialize Neo4j connection
    try:
        graph = Neo4jGraph(
            url=settings.NEO4J_URI,
            username=settings.NEO4J_USERNAME,
            password=settings.NEO4J_PASSWORD
        )
        logger.info("Successfully connected to Neo4j.")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        return

    # Idempotency check: Skip if graph is already populated
    try:
        res = graph.query("MATCH (n) RETURN count(n) AS count")
        if res and res[0]["count"] > 0:
            logger.info(f"Graph already contains {res[0]['count']} nodes. Skipping ingestion.")
            return
    except Exception as e:
        logger.warning(f"Could not check node count: {e}")

    # Initialize LLM
    llm = ChatGoogleGenerativeAI(
        model=settings.LLM_MODEL_NAME,
        temperature=0.1,
        google_api_key=settings.GOOGLE_API_KEY
    )
    extractor = llm.with_structured_output(GraphExtraction)

    data_dir = settings.DATA_PATH
    
    if not os.path.exists(data_dir):
        logger.error(f"Data directory {data_dir} not found.")
        return

    logger.info(f"Processing JSON files in {data_dir}...")
    
    # Process files
    for filename in os.listdir(data_dir):
        if not filename.endswith(".json"):
            continue
            
        filepath = os.path.join(data_dir, filename)
        logger.info(f"Extracting graph data from {filename}...")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse {filename}")
                continue
                
        # Combine text for the document (truncate to avoid massive context for LLM extraction)
        full_text = ""
        if isinstance(data, list):
            for block in data:
                if 'text' in block:
                    full_text += block['text'] + "\n"
        
        # Take a chunk of text (e.g., first 4000 characters) to extract key entities
        # A more robust system would chunk and process the entire document.
        text_chunk = full_text[:4000]
        if not text_chunk.strip():
            continue

        prompt = f"""
        Extract legal entities and their relationships from the following text to build a knowledge graph.
        Entities can be Acts, Cases, Organizations, Persons, or Legal Concepts.
        Relationships can be AMENDS, CITES, REPEALS, APPLIES_TO, or INVOLVES.
        
        Text:
        {text_chunk}
        """
        
        try:
            extraction: GraphExtraction = extractor.invoke(prompt)
            
            # Insert into Neo4j
            for node in extraction.nodes:
                # Sanitize label and properties
                label = node.label.replace(" ", "_").replace("-", "_").capitalize()
                # Create Cypher query
                # Note: simple property dict injection
                props_str = ", ".join([f"{k}: ${k}" for k in node.properties.keys()])
                props_str = f"{{{props_str}}}" if props_str else ""
                
                query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
                graph.query(query, params={"id": node.id, "props": node.properties})
                
            for rel in extraction.relationships:
                rel_type = rel.type.replace(" ", "_").replace("-", "_").upper()
                query = f"""
                MATCH (a {{id: $source_id}})
                MATCH (b {{id: $target_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $props
                """
                graph.query(query, params={"source_id": rel.source_id, "target_id": rel.target_id, "props": rel.properties})
                
            logger.info(f"Successfully inserted {len(extraction.nodes)} nodes and {len(extraction.relationships)} relationships from {filename}.")
            
        except Exception as e:
            logger.error(f"Failed to extract/insert from {filename}: {e}")

if __name__ == "__main__":
    build_graph()
