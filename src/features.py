"""Feature builders shared by training and prediction.

Three views of the ticket, used side by side:
  * word TF-IDF      -> exact words ("printer", "locked", "503")
  * char TF-IDF      -> survives typos ("pasword", "outlok")
  * sentence vector  -> meaning ("can't get in" ~ "locked out")
plus one-hot columns for the trusted dropdown fields.
"""
import os

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class SentenceEmbedder(BaseEstimator, TransformerMixin):
    """Turns text into a 384-number meaning vector (local model, no API).

    Vectors are cached by text so cross-validation doesn't re-encode the same
    sentences again and again. The loaded model is never pickled.
    """

    _shared_model = None
    _cache: dict = {}

    def __init__(self, model_name: str = EMBED_MODEL):
        self.model_name = model_name

    def _model(self):
        if SentenceEmbedder._shared_model is None:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")   # use the cached copy only
            from sentence_transformers import SentenceTransformer
            SentenceEmbedder._shared_model = SentenceTransformer(self.model_name)
        return SentenceEmbedder._shared_model

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        texts = list(X)
        missing = [t for t in dict.fromkeys(texts) if t not in self._cache]
        if missing:
            vecs = self._model().encode(missing, batch_size=64, normalize_embeddings=True,
                                        show_progress_bar=False)
            self._cache.update(zip(missing, vecs))
        return np.vstack([self._cache[t] for t in texts])


def build_features(kind: str, use_facts: bool) -> ColumnTransformer:
    """kind: 'tfidf' | 'embed' | 'all'. use_facts adds environment + who_affected."""
    parts = []
    if kind in ("tfidf", "all"):
        parts.append(("words", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1), "text"))
        parts.append(("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True, min_df=2), "text"))
    if kind in ("embed", "all"):
        parts.append(("meaning", SentenceEmbedder(), "text"))
    fact_cols = ["service", "environment", "who_affected"] if use_facts else ["service"]
    parts.append(("facts", OneHotEncoder(handle_unknown="ignore"), fact_cols))
    return ColumnTransformer(parts)
