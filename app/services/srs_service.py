from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models import UserItemProgress


@dataclass(frozen=True)
class SRSResult:
    repetitions: int
    interval_days: int
    ease_factor: float
    due_at: datetime


def calculate_next_review(progress: UserItemProgress, quality: int, now: datetime | None = None) -> SRSResult:
    if not 0 <= quality <= 5:
        raise ValueError("Review quality must be between 0 and 5")

    reviewed_at = now or datetime.now(timezone.utc)
    if quality < 3:
        repetitions = 0
        interval_days = 1
    else:
        repetitions = progress.repetitions + 1
        if repetitions == 1:
            interval_days = 1
        elif repetitions == 2:
            interval_days = 6
        else:
            interval_days = max(1, round(progress.interval_days * progress.ease_factor))

    ease_factor = max(
        1.3,
        progress.ease_factor
        + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
    )
    due_at = reviewed_at + timedelta(days=interval_days)
    return SRSResult(repetitions, interval_days, ease_factor, due_at)
