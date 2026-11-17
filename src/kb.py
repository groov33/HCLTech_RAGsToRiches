"""Knowledge-base helpers: load articles, build match cards, number the steps.

Two ideas live here:

* **Match card** = the part of an article that is SEARCHED: title + symptoms +
  error messages + keywords. Users describe symptoms ("Outlook keeps asking for
  my password"), not fixes, so the fix steps are deliberately left out of the
  searchable text.

* **Step IDs** = every fix step gets a stable address the LLM must cite:
      KB-020/self/2      -> self-help step 2 (employees may see these)
      KB-020/support/1   -> support step 1   (analysts only)
  The citation checker (src/resolve.py) uses these IDs to prove that each
  step of a recommended fix really comes from an approved article.
"""
import json
from functools import lru_cache
from pathlib import Path

KB_PATH = Path(__file__).resolve().parents[1] / "data" / "knowledge_base" / "articles.json"

# Which article access levels and step types each role may see.
# The filter is applied BEFORE search, so restricted text never reaches the
# ranking, the results or the LLM prompt.
ROLE_ACCESS = {
    "employee": {"levels": ["public"], "step_types": ["self"]},
    "support": {"levels": ["public", "internal"], "step_types": ["self", "support"]},
    "admin": {"levels": ["public", "internal"], "step_types": ["self", "support"]},
}


def access_for(role: str) -> dict:
    if role not in ROLE_ACCESS:
        raise ValueError(f"unknown role {role!r}; expected one of {list(ROLE_ACCESS)}")
    return ROLE_ACCESS[role]


@lru_cache(maxsize=1)
def load_articles(path: Path = KB_PATH) -> dict[str, dict]:
    """kb_id -> article."""
    articles = json.loads(Path(path).read_text(encoding="utf-8"))
    return {a["kb_id"]: a for a in articles}


def match_card(article: dict) -> str:
    """The searchable text of an article (symptoms, not fixes)."""
    parts = [article["title"], *article.get("symptoms", []), *article.get("error_messages", []),
             *article.get("keywords", [])]
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


def article_steps(article: dict, step_types=("self", "support")) -> list[dict]:
    """All citable steps of one article, each with its ID and exact source text."""
    kb_id = article["kb_id"]
    steps = []
    if "self" in step_types:
        for i, text in enumerate(article.get("self_help_steps", []), start=1):
            steps.append({"id": f"{kb_id}/self/{i}", "type": "self", "text": text})
    if "support" in step_types:
        for s in article.get("support_steps", []):
            text = s["do"]
            if s.get("expected"):
                text += f" (Expected: {s['expected']})"
            steps.append({"id": f"{kb_id}/support/{s['n']}", "type": "support", "text": text,
                          "do": s["do"], "expected": s.get("expected", "")})
    return steps
