"""Search past tickets and KB articles (hybrid search).

    from src.retrieve import Retriever
    r = Retriever.load()
    tickets = r.search_tickets("vpn connects but shared drive won't open", service="VPN")
    kb = r.search_kb("vpn connects but shared drive won't open", role="analyst",
                     service="VPN", subcategory="VPN problem", sub_prob=0.87)

Same recipe for both sources:
  1. FILTER   (hard)  role -> allowed access levels, plus user filters (FR-07)
  2. SEARCH   meaning search (vectors, ChromaDB) top 20 + keyword search (BM25) top 20
  3. MERGE    Reciprocal Rank Fusion: score = 1/(60 + rank_vec) + 1/(60 + rank_kw)
              -> a result high on BOTH lists wins; no score scales to tune
  4. BOOST    (soft, small) same service / same predicted subcategory
  5. KEEP     top 5 tickets, top 3 articles, each with a plain-words `why_matched`

Predicted labels only BOOST, never filter: a wrong prediction can't hide the
right article.
"""
import re
from collections import Counter

import numpy as np
from rank_bm25 import BM25Okapi

from build.build_index import chroma_client
from src.features import encode
from src.kb import access_for

POOL = 20             # candidates taken from each search before merging
RRF_K = 60            # standard RRF constant
DUPLICATE_SIM = 0.85  # a past ticket this similar in meaning = "possible duplicate"

_STOP = set("a an the and or of to in on for is it i my me we our you your this that with at be "
            "was are can can't cannot not do does don't from as by but so if when".split())


def tokenize(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP]


class _Index:
    """One searchable collection: Chroma for vectors + in-memory BM25 for keywords."""

    def __init__(self, collection):
        self.col = collection
        data = collection.get(include=["documents", "metadatas", "embeddings"])
        self.ids = data["ids"]
        self.docs = data["documents"]
        self.meta = dict(zip(self.ids, data["metadatas"]))
        self.vecs = dict(zip(self.ids, np.asarray(data["embeddings"])))
        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs])

    def search(self, query: str, where: dict | None, allowed=lambda m: True) -> list[dict]:
        qvec = encode([query])[0]

        # meaning search: ChromaDB applies the metadata filter BEFORE ranking
        res = self.col.query(query_embeddings=[qvec.tolist()], n_results=POOL, where=where or None)
        vec_ids = res["ids"][0]

        # keyword search: same filter, applied in Python
        kw_scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted((i for i in range(len(self.ids)) if allowed(self.meta[self.ids[i]])),
                        key=lambda i: -kw_scores[i])
        kw_ids = [self.ids[i] for i in ranked[:POOL] if kw_scores[i] > 0]

        # merge by rank (RRF)
        rrf = Counter()
        for ids in (vec_ids, kw_ids):
            for rank, doc_id in enumerate(ids, start=1):
                rrf[doc_id] += 1 / (RRF_K + rank)
        return [{"id": d, "rrf": s,
                 "similarity": round(float(self.vecs[d] @ qvec), 3),   # cosine, 0..1 in practice
                 "in_vector": d in vec_ids, "in_keyword": d in kw_ids,
                 "meta": self.meta[d]}
                for d, s in rrf.items()]


def _where(filters: dict) -> dict | None:
    """{"service": "VPN", "priority": "P1"} -> Chroma where clause."""
    clauses = [{k: v} for k, v in filters.items() if v]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _how(hit: dict) -> str:
    return "meaning + keywords" if hit["in_vector"] and hit["in_keyword"] else (
        "meaning" if hit["in_vector"] else "keywords")


class Retriever:
    def __init__(self, client=None):
        client = client or chroma_client()
        self.tickets = _Index(client.get_collection("tickets"))
        self.kb = _Index(client.get_collection("kb_articles"))

    @classmethod
    def load(cls) -> "Retriever":
        return cls()

    # ------------------------------------------------------------------ tickets
    def search_tickets(self, query: str, service: str | None = None, filters: dict | None = None,
                       k: int = 5) -> dict:
        """Similar past tickets + their vote.

        Only the service the USER gave is used as a boost (never the classifier's
        prediction), so the vote stays an independent second opinion.
        """
        filters = filters or {}
        hits = self.tickets.search(query, _where(filters),
                                   allowed=lambda m: all(m.get(f) == v for f, v in filters.items() if v))
        for h in hits:
            same_service = service and h["meta"]["service"] == service
            h["score"] = h["rrf"] * (1.15 if same_service else 1.0)
            why = [f"similar by {_how(h)} ({h['similarity']:.0%})"]
            if same_service:
                why.append(f"same service {service}")
            h["why_matched"] = " · ".join(why)
            h["possible_duplicate"] = h["similarity"] >= DUPLICATE_SIM
        hits = sorted(hits, key=lambda h: -h["score"])[:k]

        cats = Counter(h["meta"]["category"] for h in hits)      # ties -> higher-ranked ticket wins
        subs = Counter(h["meta"]["subcategory"] for h in hits)
        return {
            "hits": [{"ticket_id": h["id"], "description": h["meta"]["description"],
                      "service": h["meta"]["service"], "category": h["meta"]["category"],
                      "subcategory": h["meta"]["subcategory"], "priority": h["meta"]["priority"],
                      "similarity": h["similarity"], "why_matched": h["why_matched"],
                      "possible_duplicate": h["possible_duplicate"]} for h in hits],
            "vote_category": cats.most_common(1)[0][0] if hits else None,
            "vote_subcategory": subs.most_common(1)[0][0] if hits else None,
        }

    # ---------------------------------------------------------------------- KB
    def search_kb(self, query: str, role: str = "analyst", service: str | None = None,
                  subcategory: str | None = None, sub_prob: float = 0.0, k: int = 3) -> dict:
        """Top KB articles the role may see, plus signals for the decision step."""
        levels = access_for(role)["levels"]
        hits = self.kb.search(query, {"access_level": {"$in": levels}},
                              allowed=lambda m: m["access_level"] in levels)
        for h in hits:
            m, boost, why = h["meta"], 1.0, [f"symptoms match by {_how(h)} ({h['similarity']:.0%})"]
            if subcategory and m["subcategory"] == subcategory:
                boost *= 1 + 0.2 * sub_prob
                why.append(f"subcategory {subcategory} ({sub_prob:.0%})")
            if service and service in m["services"].split("|"):
                boost *= 1.1
                why.append(f"covers service {service}")
            h["score"], h["why_matched"] = h["rrf"] * boost, " · ".join(why)
        hits = sorted(hits, key=lambda h: -h["score"])[:k]

        top = [{"kb_id": h["id"], "title": h["meta"]["title"], "subcategory": h["meta"]["subcategory"],
                "access_level": h["meta"]["access_level"], "similarity": h["similarity"],
                "why_matched": h["why_matched"]} for h in hits]
        # signals for src/decide.py
        conflict = (len(hits) > 1 and hits[1]["score"] >= 0.9 * hits[0]["score"]
                    and hits[0]["meta"]["subcategory"] != hits[1]["meta"]["subcategory"])
        return {"hits": top,
                "kb_best": top[0]["similarity"] if top else 0.0,   # how well the #1 article matches
                "conflict": conflict}
