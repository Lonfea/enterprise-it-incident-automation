from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


RUNBOOK_PATH = Path(__file__).resolve().parents[1] / "data" / "runbooks.json"


@dataclass(frozen=True)
class RunbookGuidance:
    runbook_id: str
    title: str
    category: str
    relevance_score: float
    actions: list[str]
    safeguards: list[str]
    requires_human_approval: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def load_runbooks() -> list[dict]:
    return json.loads(RUNBOOK_PATH.read_text(encoding="utf-8"))


def _document(runbook: dict) -> str:
    return " ".join(
        [runbook["category"], runbook["title"], *runbook["symptoms"], *runbook["actions"]]
    )


def retrieve_guidance(incident: dict) -> RunbookGuidance:
    """Retrieve the most relevant operational runbook without executing any action."""
    runbooks = load_runbooks()
    query = " ".join(
        str(incident.get(key, "")) for key in ("category", "service", "message", "explanation")
    )
    documents = [_document(runbook) for runbook in runbooks]
    matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2)).fit_transform(
        [*documents, query]
    )
    scores = cosine_similarity(matrix[-1], matrix[:-1]).ravel()

    category = str(incident.get("category", ""))
    for index, runbook in enumerate(runbooks):
        if runbook["category"] == category:
            scores[index] += 0.35

    best_index = int(scores.argmax())
    selected = runbooks[best_index]
    return RunbookGuidance(
        runbook_id=selected["id"],
        title=selected["title"],
        category=selected["category"],
        relevance_score=round(min(float(scores[best_index]), 1.0), 3),
        actions=selected["actions"],
        safeguards=selected["safeguards"],
    )
