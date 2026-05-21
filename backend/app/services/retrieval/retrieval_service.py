import os
import logging
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.config import settings

logger = logging.getLogger(__name__)

class RetrievalService:
    def __init__(self):
        logger.info(f"Loading Local LankaLawBot Database from: {settings.CHROMA_PATH}")
        
        # Load the embedding model
        self.embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
        
        # Connect to local ChromaDB
        self.vector_store = Chroma(
            persist_directory=settings.CHROMA_PATH, 
            embedding_function=self.embeddings
        )

    def search(
        self, 
        query: str, 
        top_k: int = 5, 
        expand_parents: bool = True,
        year_filter: int | None = None,
        act_name_filter: str | None = None,
        **kwargs
    ):
        """Executes Parent-Child RAG strategy using local ChromaDB."""
        logger.info(f"🔍 Searching local database for: '{query}'")
        
        filter_dict = {"chunk_type": "child"}
        if year_filter:
            filter_dict["year"] = year_filter
        if act_name_filter:
            filter_dict["act_name"] = act_name_filter

        child_results = self.vector_store.similarity_search(
            query, 
            k=top_k, 
            filter=filter_dict
        )
        
        if not expand_parents:
            return [{"child": doc, "parent": None} for doc in child_results]

        parent_ids = set()
        for doc in child_results:
            p_id = doc.metadata.get("parent_id")
            if p_id and p_id != "None":
                parent_ids.add(p_id)
                
        if not parent_ids:
            return []
            
        parents_data = self.vector_store.get(
            where={"citation_id": {"$in": list(parent_ids)}}
        )
        
        final_results = []
        for i in range(len(parents_data['ids'])):
            parent_doc = {
                "page_content": parents_data['documents'][i],
                "metadata": parents_data['metadatas'][i]
            }
            final_results.append({
                "child": None,
                "parent": parent_doc
            })
            
        return final_results

_instance = None
def get_retrieval_service():
    global _instance
    if _instance is None:
        _instance = RetrievalService()
    return _instance