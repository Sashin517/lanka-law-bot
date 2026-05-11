import chromadb

client = chromadb.PersistentClient(path="./database/chroma_db")
collections = client.list_collections()

if not collections:
    print("No collections found.")
else:
    for collection in collections:
        print(f"\n--- Collection: {collection.name} ---")
        unique_titles = set()
        batch_size = 5000
        offset = 0
        
        while True:
            results = collection.get(
                include=["metadatas"],
                limit=batch_size,
                offset=offset
            )
            
            metadatas = results.get("metadatas")
            if not metadatas:
                break
                
            for meta in metadatas:
                if meta:
                    # Look for common fields that indicate the document name
                    title = meta.get("title") or meta.get("source") or meta.get("document_id")
                    if title:
                        unique_titles.add(title)
                        
            if len(metadatas) < batch_size:
                break
                
            offset += batch_size
            
        print(f"Found {len(unique_titles)} unique acts/documents:")
        for t in sorted(unique_titles):
            print(f"- {t}")
