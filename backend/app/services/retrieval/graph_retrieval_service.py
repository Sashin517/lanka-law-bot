import logging
from typing import List, Dict, Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_neo4j import Neo4jGraph
from app.core.config import settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class GraphEntityExtraction(BaseModel):
    entities: List[str] = Field(description="Key entities extracted from the query, such as Act names or Case names.")

class GraphRetrievalService:
    def __init__(self) -> None:
        logger.info("Initialising GraphRetrievalService ...")
        try:
            self._graph = Neo4jGraph(
                url=settings.NEO4J_URI,
                username=settings.NEO4J_USERNAME,
                password=settings.NEO4J_PASSWORD
            )
            self._is_connected = True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j Graph DB: {e}")
            self._is_connected = False

        self._llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL_NAME,
            temperature=0,
            google_api_key=settings.GOOGLE_API_KEY
        )
        self._extractor = self._llm.with_structured_output(GraphEntityExtraction)

    def search(self, query: str) -> str:
        """
        Extracts entities from the user query, searches the Neo4j graph for those entities,
        and returns a string representation of the retrieved relationships.
        """
        if not self._is_connected:
            return ""

        try:
            # 1. Extract entities from query
            extraction = self._extractor.invoke(f"Extract key legal entities (Act names, Case names, Persons, Organizations) from this query: {query}")
            entities = extraction.entities

            if not entities:
                return ""

            # 2. Query the graph for each entity
            context_pieces = []
            
            for entity in entities:
                # Basic Cypher query: find the node with matching id (case-insensitive fuzzy match via CONTAINS or exact)
                # Then get 1-hop relationships
                cypher = """
                MATCH (n)-[r]->(m)
                WHERE toLower(n.id) CONTAINS toLower($entity) OR toLower(m.id) CONTAINS toLower($entity)
                RETURN n.id AS source, type(r) AS relationship, m.id AS target, properties(r) AS rel_props
                LIMIT 10
                """
                
                results = self._graph.query(cypher, params={"entity": entity})
                
                for record in results:
                    source = record.get("source")
                    rel = record.get("relationship")
                    target = record.get("target")
                    context_pieces.append(f"- {source} {rel} {target}")
            
            if not context_pieces:
                return ""
                
            # Remove duplicates
            context_pieces = list(set(context_pieces))
            
            graph_context = "Graph Relational Context:\n" + "\n".join(context_pieces)
            logger.info(f"Graph retrieval found {len(context_pieces)} relations.")
            
            return graph_context

        except Exception as e:
            logger.error(f"Graph retrieval failed: {e}")
            return ""

_instance: GraphRetrievalService | None = None

def get_graph_retrieval_service() -> GraphRetrievalService:
    global _instance
    if _instance is None:
        _instance = GraphRetrievalService()
    return _instance
