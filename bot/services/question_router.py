import random
from bot.db.models import Question


def pick_next_question(
    all_questions: list[Question],
    asked_ids: list[str],
    topic_coverage: dict[str, int],
    selected_pack: str | None = None,
    last_tags: list[str] | None = None,
) -> Question | None:
    """Select the next interview question using deterministic scoring.

    Priority:
    1. Filter out already-asked questions
    2. If user selected a pack — filter to that pack
    3. Prefer packs with least coverage
    4. Prefer easy difficulty, then medium
    5. Prefer low emotional intensity
    6. Avoid same tags as the last question
    """
    candidates = [q for q in all_questions if q.id not in asked_ids]
    if not candidates:
        return None

    if selected_pack:
        pack_candidates = [q for q in candidates if q.pack == selected_pack]
        if pack_candidates:
            candidates = pack_candidates

    last_tags = set(last_tags or [])

    def score(q: Question) -> tuple:
        pack_count = sum(topic_coverage.get(t, 0) for t in (q.tags or []))
        difficulty_score = 0 if q.difficulty == "easy" else 1
        intensity_score = {"low": 0, "medium": 1, "high": 2}.get(q.emotional_intensity, 1)
        tag_overlap = len(set(q.tags or []) & last_tags)
        return (pack_count, difficulty_score, intensity_score, tag_overlap)

    candidates.sort(key=score)

    top_bucket = candidates[:max(3, len(candidates) // 5)]
    return random.choice(top_bucket)


def get_followup(question: Question, index: int = 0) -> str | None:
    """Get a follow-up question from the template list."""
    followups = question.followups or []
    if index < len(followups):
        return followups[index]
    return None
