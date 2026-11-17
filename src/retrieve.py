"""Search past tickets and KB articles (hybrid search).

    from src.retrieve import Retriever
    r = Retriever.load()
    tickets = r.search_tickets("vpn connects but shared drive won't open", service="VPN")
    kb = r.search_kb("vpn connects but shared drive won't open", role="support",
                     service="VPN", subcategory="VPN problem", sub_prob=0.87)

Same recipe for both sources:
  1. FILTER   (hard)  role -> allowed access levels, plus user filters (FR-07)
  2. SEARCH   meaning search (vectors, ChromaDB) top 20 [+ keyword search (BM25) top 20]
  3. MERGE    Reciprocal Rank Fusion: score = 1/(60 + rank_vec) + 1/(60 + rank_kw)
              (only in "hybrid" mode; the default is "vector", see SEARCH_MODE below)
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
from src.kb import access_for, article_steps, load_articles
from src.text import mask_pii

# Measured on 180 held-out tickets (reports/RAG_EVALUATION.md): meaning search alone beat
# hybrid (ticket MRR 0.955 vs 0.917, KB Hit@3 93.9% vs 89.4%). Our tickets are paraphrased,
# so exact-word matches mostly added noise. Keyword search stays in the code for the
# comparison table; set this to "hybrid" to use RRF again (e.g. for data full of error codes).
SEARCH_MODE = "vector"
POOL = 20             # candidates taken from each search before merging
RRF_K = 60            # standard RRF constant
DUPLICATE_SIM = 0.85  # a past ticket this similar in meaning = "possible duplicate"
KB_FLOOR = 0.20      # best article below this = clearly unrelated (5th percentile of real tickets: 0.19)

# Two problems in one ticket: split into clauses, search the KB per clause. Two clauses that each
# match a DIFFERENT subcategory's article this strongly = probably two problems -> REVIEW.
# Measured (reports/RAG_EVALUATION.md §4): catches 5 of 6 hand-written two-problem tickets and
# fires on 4 of 360 held-out one-problem tickets (1.1%). At 0.55 it caught only 1 of 6.
SECOND_PROBLEM_SCORE = 0.50
CLAUSE_SPLIT = re.compile(r"[.!?;]+\s+|\b(?:and also|and separately|separately|also|as well as|plus|"
                          r"another (?:issue|problem|thing) is|and)\b", re.I)

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

    def search(self, query: str, where: dict | None, allowed=lambda m: True, mode: str = SEARCH_MODE) -> list[dict]:
        qvec = encode([query])[0]

        # meaning search: ChromaDB applies the metadata filter BEFORE ranking
        res = self.col.query(query_embeddings=[qvec.tolist()], n_results=POOL, where=where or None)
        vec_ids = res["ids"][0]

        # keyword search: same filter, applied in Python
        kw_scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted((i for i in range(len(self.ids)) if allowed(self.meta[self.ids[i]])),
                        key=lambda i: -kw_scores[i])
        kw_ids = [self.ids[i] for i in ranked[:POOL] if kw_scores[i] > 0]

        # merge by rank (RRF). mode lets the evaluation compare each search on its own.
        lists = {"vector": [vec_ids], "keyword": [kw_ids], "hybrid": [vec_ids, kw_ids]}[mode]
        rrf = Counter()
        for ids in lists:
            for rank, doc_id in enumerate(ids, start=1):
                rrf[doc_id] += 1 / (RRF_K + rank)
        return [{"id": d, "rrf": s,
                 "similarity": round(float(self.vecs[d] @ qvec), 3),   # cosine, 0..1 in practice
                 "in_vector": any(d in ids for ids in lists if ids is vec_ids),     # only lists that
                 "in_keyword": any(d in ids for ids in lists if ids is kw_ids),     # were really used
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
                       k: int = 5, mode: str = SEARCH_MODE) -> dict:
        """Similar past tickets + their vote  ->  contracts.SimilarTicketsResult.

        Only the service the USER gave is used as a boost (never the classifier's
        prediction), so the vote stays an independent second opinion.
        """
        filters = filters or {}
        hits = self.tickets.search(query, _where(filters),
                                   allowed=lambda m: all(m.get(f) == v for f, v in filters.items() if v), mode=mode)
        for h in hits:
            same_service = bool(service) and h["meta"]["service"] == service
            h["rank_score"] = h["rrf"] * (1.15 if same_service else 1.0)
            h["why"] = [f"similar by {_how(h)} ({h['similarity']:.0%})"] + (
                [f"same service: {service}"] if same_service else [])
        hits = sorted(hits, key=lambda h: -h["rank_score"])[:k]

        tickets = [{"ticket_id": h["id"], "excerpt": mask_pii(h["meta"]["description"]),
                    "score": h["similarity"], "category": h["meta"]["category"],
                    "subcategory": h["meta"]["subcategory"], "priority": h["meta"]["priority"],
                    "why_matched": h["why"], "is_duplicate": h["similarity"] >= DUPLICATE_SIM}
                   for h in hits]
        vote = None
        if tickets:                                   # ties -> the higher-ranked ticket's category wins
            category, count = Counter(t["category"] for t in tickets).most_common(1)[0]
            vote = {"category": category, "agree_count": count, "of": len(tickets)}
        return {"tickets": tickets, "vote": vote}

    # ---------------------------------------------------------------------- KB
    def search_kb(self, query: str, role: str = "support", service: str | None = None,
                  subcategory: str | None = None, sub_prob: float = 0.0, k: int = 3,
                  mode: str = SEARCH_MODE) -> dict:
        """Top KB articles the role may see + signals  ->  contracts.KBSearchResult."""
        access = access_for(role)
        levels = access["levels"]
        hits = self.kb.search(query, {"access_level": {"$in": levels}},
                              allowed=lambda m: m["access_level"] in levels, mode=mode)
        for h in hits:
            m, boost = h["meta"], 1.0
            h["why"] = [f"symptoms match by {_how(h)} ({h['similarity']:.0%})"]
            if subcategory and m["subcategory"] == subcategory:
                boost *= 1 + 0.2 * sub_prob
                h["why"].append(f"predicted subcategory: {subcategory} ({sub_prob:.0%})")
            if service and service in m["services"].split("|"):
                boost *= 1.1
                h["why"].append(f"covers service: {service}")
            h["rank_score"] = h["rrf"] * boost
        hits = sorted(hits, key=lambda h: -h["rank_score"])[:k]

        articles = load_articles()
        top = []
        for h in hits:
            a = articles[h["id"]]
            top.append({"kb_id": a["kb_id"], "title": a["title"], "subcategory": a["subcategory"],
                        "access_level": a["access_level"], "score": h["similarity"], "why_matched": h["why"],
                        "steps": [{"step_id": s["id"], "text": s["text"]}            # role-filtered
                                  for s in article_steps(a, access["step_types"])],
                        "verify": a["verify"], "escalate_when": a["escalate_when"]})
        best = top[0]["score"] if top else 0.0                 # how well the #1 article matches
        conflict = (len(hits) > 1 and hits[1]["rank_score"] >= 0.9 * hits[0]["rank_score"]
                    and hits[0]["meta"]["subcategory"] != hits[1]["meta"]["subcategory"])

        # Knowledge gap, two checks (the LLM can still declare one later):
        #  1. nothing is even close in meaning, or
        #  2. no article is written for this kind of problem on this service
        #     (e.g. "Wrong data" on Payroll System). Similarity alone can't see this:
        #     a Finance "wrong data" article reads close to a payroll one, but its steps don't apply.
        gap_reason = None
        if best < KB_FLOOR:
            gap_reason = "no KB article is close to this ticket"
        elif subcategory and not _covered(articles, levels, subcategory, service):
            gap_reason = (f"no KB article covers '{subcategory}'"
                          + (f" on {service}" if service and service != ANY_SERVICE else ""))
        return {"articles": top, "best_score": best, "conflict": conflict,
                "knowledge_gap": gap_reason is not None, "gap_reason": gap_reason}

    def distinct_problems(self, text: str, role: str = "support") -> list[dict]:
        """One entry per different subcategory that some clause of the ticket matches strongly.

        2+ entries = the ticket probably describes two problems, and one confident fix
        would silently ignore the other. Clauses under 4 words are skipped (too little to match).
        """
        found = {}
        for clause in CLAUSE_SPLIT.split(text):
            clause = clause.strip(" ,")
            if len(clause.split()) < 4:
                continue
            kb = self.search_kb(clause, role=role)
            if kb["articles"] and kb["best_score"] >= SECOND_PROBLEM_SCORE:
                a = kb["articles"][0]
                found.setdefault(a["subcategory"], {"subcategory": a["subcategory"], "clause": clause,
                                                    "kb_id": a["kb_id"], "score": kb["best_score"]})
        return list(found.values())


ANY_SERVICE = "Other / Not sure"   # the user didn't know the service: only the subcategory is checked


def _covered(articles: dict, levels: list[str], subcategory: str, service: str | None) -> bool:
    """Is there at least one article (that this role may see) for this subcategory on this service?"""
    return any(a["subcategory"] == subcategory and a["access_level"] in levels
               and (not service or service == ANY_SERVICE or service in a["services"])
               for a in articles.values())
