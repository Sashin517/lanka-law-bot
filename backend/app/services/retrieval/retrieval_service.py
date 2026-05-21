import os
import logging
from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from app.core.config import settings

logger = logging.getLogger(__name__)

class RetrievalService:
    def __init__(self):
        logger.info(f"Loading Local LankaLawBot Database from: {settings.CHROMA_PATH}")
        
        self.embeddings = HuggingFaceEmbeddings(model_name=settings.EMBEDDING_MODEL)
        
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
            return [
                {
                    "child": doc,
                    "parent": None,
                    "metadata": doc.metadata,
                    "page_content": doc.page_content
                } for doc in child_results
            ]

        # Map parent IDs to their triggering child documents
        parent_id_to_child = {}
        for doc in child_results:
            p_id = doc.metadata.get("parent_id")
            if p_id and p_id != "None" and p_id not in parent_id_to_child:
                parent_id_to_child[p_id] = doc
                
        if not parent_id_to_child:
            return [
                {
                    "child": doc,
                    "parent": None,
                    "metadata": doc.metadata,
                    "page_content": doc.page_content
                } for doc in child_results
            ]
            
        # Retrieve full parent chunks
        parents_data = self.vector_store.get(
            where={"citation_id": {"$in": list(parent_id_to_child.keys())}}
        )
        
        final_results = []
        for i in range(len(parents_data['ids'])):
            p_meta = parents_data['metadatas'][i]
            p_content = parents_data['documents'][i]
            
            # Reconstruct the LangChain Document object
            parent_doc = Document(page_content=p_content, metadata=p_meta)
            
            # Match it back to the child that found it
            p_id = p_meta.get("citation_id")
            child_doc = parent_id_to_child.get(p_id)

            # Flat dictionary structure to satisfy context_assembler.py 
            # while keeping child/parent objects for LangGraph node deduplication
            final_results.append({
                "child": child_doc,
                "parent": parent_doc,
                "metadata": p_meta,
                "page_content": p_content
            })
            
        return final_results

_instance = None
def get_retrieval_service():
    global _instance
    if _instance is None:
        _instance = RetrievalService()
    return _instance