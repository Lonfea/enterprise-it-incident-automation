"""Learn which alert templates operators consistently reject.

A template is suppressed only after enough verdicts agree, so one mistaken
click cannot silence a class of alerts, and any confirmed incident on a
template keeps it alerting.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

MIN_VERDICTS = 3
MAX_INCIDENT_RATE = 0.0


def noise_templates(
    verdicts: Iterable[tuple[str, bool]],
    min_verdicts: int = MIN_VERDICTS,
    max_incident_rate: float = MAX_INCIDENT_RATE,
) -> set[str]:
    """Return templates whose verdicts are mostly "not an incident".

    ``verdicts`` yields ``(template, was_real_incident)`` pairs.
    """
    totals: Counter[str] = Counter()
    real: Counter[str] = Counter()
    for template, was_real in verdicts:
        totals[template] += 1
        real[template] += int(was_real)
    return {
        template
        for template, count in totals.items()
        if count >= min_verdicts and real[template] / count <= max_incident_rate
    }


def load_noise_templates(session: Session) -> set[str]:
    from .database import IncidentFeedback

    rows = session.execute(select(IncidentFeedback.template, IncidentFeedback.verdict)).all()
    return noise_templates((template, verdict == "true_positive") for template, verdict in rows)
