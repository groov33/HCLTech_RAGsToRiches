"""Build the two search indexes: past tickets and KB articles.

Run from the project root, AFTER build.train_models (it needs the split):
    python -m build.build_index

What goes in
  * tickets    : every ticket EXCEPT the test split, so evaluation tickets can't
                 find themselves. Searched text = clean_description(description).
  * kb         : one entry per article. Searched text = its match card
                 (title + symptoms + error messages + keywords, see src/kb.py).

How it is stored
  * ChromaDB (data/store/chroma): vectors + metadata, cosine distance. Metadata
    holds the fields we filter on (access_level, service, category, ...).
  * The keyword (BM25) index is rebuilt in memory from the same documents when
    the retriever loads: ~1,000 short texts take milliseconds, so there is
    nothing extra to keep in sync on disk.

Vectors are computed by us with all-MiniLM-L6-v2 (the classifier's model) and
passed to Chroma, so Chroma never downloads its own embedding model.
"""
import json
import shutil
import sys
import time
from pathlib import Path

from build.train_models import SPLIT_PATH, load_tickets
from src.features import encode
from src.kb import load_articles, match_card

ROOT = Path(__file__).resolve().parents[1]
CHROMA_PATH = ROOT / "data" / "store" / "chroma"
TICKET_META = ["service", "environment", "who_affected", "category", "subcategory",
               "symptom_type", "team", "priority"]


def chroma_client(path: Path = CHROMA_PATH):
    import chromadb
    from chromadb.config import Settings
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def new_collection(client, name: str):
    return client.create_collection(name, configuration={"hnsw": {"space": "cosine"}})


def add_batched(col, ids, docs, metas, vecs, batch=500):
    for i in range(0, len(ids), batch):
        col.add(ids=ids[i:i + batch], documents=docs[i:i + batch], metadatas=metas[i:i + batch],
                embeddings=vecs[i:i + batch].tolist())


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    t0 = time.time()
    if not SPLIT_PATH.exists():
        sys.exit("No split found: run `python -m build.train_models` first.")
    split = json.loads(SPLIT_PATH.read_text())

    if CHROMA_PATH.exists():                      # always rebuild from scratch
        shutil.rmtree(CHROMA_PATH)
    client = chroma_client()

    # --- tickets: everything except the held-out test set ------------------------
    df = load_tickets()
    df = df[~df["ticket_id"].isin(set(split["test"]) | set(split.get("dropped_rule_mismatch", [])))]
    docs = df["text"].tolist()
    metas = [{k: r[k] for k in TICKET_META} | {"description": r["description"]}
             for r in df.to_dict("records")]
    vecs = encode(docs)
    add_batched(new_collection(client, "tickets"), df["ticket_id"].tolist(), docs, metas, vecs)
    print(f"tickets: indexed {len(docs)} (test split of {len(split['test'])} left out)")

    # --- KB: one match card per article ------------------------------------------
    articles = list(load_articles().values())
    cards = [match_card(a) for a in articles]
    metas = [{"kb_id": a["kb_id"], "title": a["title"], "category": a["category"],
              "subcategory": a["subcategory"], "access_level": a["access_level"],
              "services": "|".join(a["services"])} for a in articles]
    add_batched(new_collection(client, "kb_articles"), [a["kb_id"] for a in articles], cards, metas, encode(cards))
    levels = {lvl: sum(a["access_level"] == lvl for a in articles) for lvl in ("public", "internal")}
    print(f"kb: indexed {len(articles)} articles {levels}")
    print(f"Saved {CHROMA_PATH.relative_to(ROOT)}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
