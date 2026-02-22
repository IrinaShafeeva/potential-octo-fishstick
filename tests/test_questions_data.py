"""Validate the questions.json data file for correctness and completeness."""
import json
from pathlib import Path

import pytest

QUESTIONS_PATH = Path(__file__).parent.parent / "bot" / "data" / "questions.json"

VALID_PACKS = {
    "childhood", "parents_home", "school", "youth", "work",
    "love", "children_family", "places", "hardships",
    "achievements", "traditions", "favorites", "later_years",
}


@pytest.fixture
def questions():
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestQuestionsData:
    def test_file_exists(self):
        assert QUESTIONS_PATH.exists()

    def test_is_list(self, questions):
        assert isinstance(questions, list)

    def test_minimum_count(self, questions):
        assert len(questions) >= 50

    def test_all_have_required_fields(self, questions):
        required = {"id", "pack", "text", "difficulty", "emotional_intensity", "tags", "followups"}
        for q in questions:
            missing = required - set(q.keys())
            assert not missing, f"Question {q.get('id', '?')} missing fields: {missing}"

    def test_all_packs_valid(self, questions):
        for q in questions:
            assert q["pack"] in VALID_PACKS, f"Invalid pack '{q['pack']}' in {q['id']}"

    def test_all_packs_covered(self, questions):
        packs_found = {q["pack"] for q in questions}
        missing = VALID_PACKS - packs_found
        assert not missing, f"Packs without questions: {missing}"

    def test_unique_ids(self, questions):
        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids)), "Duplicate question IDs found"

    def test_difficulty_values(self, questions):
        for q in questions:
            assert q["difficulty"] in ("easy", "medium"), f"Bad difficulty in {q['id']}"

    def test_emotional_intensity_values(self, questions):
        for q in questions:
            assert q["emotional_intensity"] in ("low", "medium", "high"), \
                f"Bad emotional_intensity in {q['id']}"

    def test_tags_are_lists(self, questions):
        for q in questions:
            assert isinstance(q["tags"], list), f"Tags not a list in {q['id']}"
            assert len(q["tags"]) > 0, f"Empty tags in {q['id']}"

    def test_followups_are_lists(self, questions):
        for q in questions:
            assert isinstance(q["followups"], list), f"Followups not a list in {q['id']}"

    def test_text_not_empty(self, questions):
        for q in questions:
            assert len(q["text"].strip()) > 10, f"Too short text in {q['id']}"

    def test_each_pack_has_minimum_questions(self, questions):
        from collections import Counter
        pack_counts = Counter(q["pack"] for q in questions)
        for pack, count in pack_counts.items():
            assert count >= 3, f"Pack '{pack}' has only {count} questions (min 3)"
