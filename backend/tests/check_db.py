import chromadb

# Initialize the Chroma client pointing to the local database folder
client = chromadb.PersistentClient(path="./database/chroma_db")

collections = client.list_collections()

if not collections:
    print("The database has no collections.")
else:
    for collection in collections:
        print(f"Collection '{collection.name}' has {collection.count()} chunks of data.")
