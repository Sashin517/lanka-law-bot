# Pinecone BM25 FTS Backfill Colab Cells

Run these cells after `/content/chunked_data/all_chunks.json` has been created by
the existing legal-corpus parsing and chunking notebook. Do not re-parse PDFs if
that file is the same canonical chunk output used for the dense index.

```python
!pip install -q --upgrade pinecone==9.0.0 tqdm
```

```python
import os
import json
import time
from tqdm.notebook import tqdm
from pinecone import Pinecone

PINECONE_API_KEY = os.environ["PINECONE_API_KEY"]
BM25_INDEX_NAME = "lawdex-legal-bm25-index"
NAMESPACE = "legal_corpus"
BATCH_SIZE = 50

pc = Pinecone(api_key=PINECONE_API_KEY)
```

```python
existing_names = [idx.name for idx in pc.preview.indexes.list()]

if BM25_INDEX_NAME not in existing_names:
    pc.preview.indexes.create(
        name=BM25_INDEX_NAME,
        deployment={
            "deployment_type": "managed",
            "cloud": "aws",
            "region": "us-east-1",
        },
        schema={
            "fields": {
                "text": {
                    "type": "string",
                    "full_text_search": {},
                }
            }
        },
        deletion_protection="disabled",
    )

    while True:
        desc = pc.preview.indexes.describe(BM25_INDEX_NAME)
        print("BM25 index status:", desc.status)
        if getattr(desc.status, "ready", False):
            break
        time.sleep(10)

bm25_index = pc.preview.index(name=BM25_INDEX_NAME)
print("BM25 host:", pc.preview.indexes.describe(BM25_INDEX_NAME).host)
```

```python
with open("/content/chunked_data/all_chunks.json", "r", encoding="utf-8") as f:
    all_chunks = json.load(f)

def clean_metadata(meta):
    clean = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, list):
            clean[k] = [str(x) for x in v if x is not None]
        else:
            clean[k] = v
    return clean

documents = []
for chunk in all_chunks:
    documents.append({
        "_id": chunk["id"],
        "text": chunk["text"],
        **clean_metadata(chunk["metadata"]),
    })

deduped_by_id = {}
duplicate_ids = set()
conflicting_duplicate_ids = set()

for document in documents:
    doc_id = document["_id"]
    existing = deduped_by_id.get(doc_id)
    if existing is not None:
        duplicate_ids.add(doc_id)
        if existing.get("text") != document.get("text"):
            conflicting_duplicate_ids.add(doc_id)

    # Keep the last record for parity with dense upsert overwrite semantics.
    deduped_by_id[doc_id] = document

documents = list(deduped_by_id.values())

print(f"Prepared {len(documents)} unique BM25 documents")
print(f"Skipped {len(duplicate_ids)} duplicate _id values")
if conflicting_duplicate_ids:
    print(
        "WARNING: duplicate _id values with different text:",
        len(conflicting_duplicate_ids),
    )
    print("Example conflicting IDs:", list(conflicting_duplicate_ids)[:5])

print(documents[0].keys())
```

```python
for i in tqdm(range(0, len(documents), BATCH_SIZE), desc="Upserting BM25 docs"):
    batch = documents[i:i + BATCH_SIZE]
    try:
        bm25_index.documents.upsert(namespace=NAMESPACE, documents=batch)
        time.sleep(0.5)
    except Exception as exc:
        print(f"Error on batch {i}-{i + len(batch)}:", exc)
        raise

print("--- BM25 upsert complete ---")
```

```python
results = bm25_index.documents.search(
    namespace=NAMESPACE,
    top_k=10,
    score_by=[{"type": "text", "field": "text", "query": "contract termination damages"}],
    include_fields=["*"],
    filter={"chunk_type": {"$eq": "child"}},
)

for match in results.matches[:3]:
    print(match.id, match.score, match.get("chunk_type"), match.get("source_filename"))
    print((match.get("text") or "")[:300])
    print("---")
```

Set `PINECONE_LEGAL_BM25_INDEX_HOST` in the backend `.env` to the printed BM25
host after the backfill succeeds.
