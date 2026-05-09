from __future__ import annotations

from app.services.user_document_vector_store import UserDocumentVectorStore


def main() -> None:
    store = UserDocumentVectorStore()
    store.ensure_collection()
    print(f"Qdrant collection ready: {store.collection}")


if __name__ == "__main__":
    main()
