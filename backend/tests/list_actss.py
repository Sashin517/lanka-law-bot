import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


def main():
    TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
    BACKEND_DIR = os.path.dirname(TESTS_DIR)
    CHROMA_PATH = os.path.join(BACKEND_DIR, "database", "chroma_db")

    if not os.path.exists(CHROMA_PATH):
        print(f"Error: Chroma database not found at {CHROMA_PATH}")
        return

    print("Loading vector database... (this may take a few seconds)")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)

    # Fetch all metadata from Chroma
    print("Extracting metadata... (using batches to avoid memory limits)")

    unique_acts = set()
    total_chunks = 0
    batch_size = 5000
    offset = 0

    while True:
        results = db.get(include=["metadatas"], limit=batch_size, offset=offset)
        metadatas = results.get("metadatas", [])
        if not metadatas:
            break

        total_chunks += len(metadatas)
        for meta in metadatas:
            if meta and "title" in meta:
                year = meta.get("year", "")
                title = meta.get("title")
                if year and str(year) not in title:
                    unique_acts.add(f"{title} ({year})")
                else:
                    unique_acts.add(title)

        offset += batch_size

    print("\n" + "=" * 50)
    print(
        f"Found {len(unique_acts)} unique Acts/Laws across {total_chunks} vector chunks:"
    )
    print("=" * 50)

    for idx, act in enumerate(sorted(unique_acts), 1):
        print(f"{idx}. {act}")


if __name__ == "__main__":
    main()
