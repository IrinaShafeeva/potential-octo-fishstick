import pytest

from bot.db.models import Question
from bot.services.question_router import pick_next_question, get_followup


class TestPickNextQuestion:
    def test_returns_question_when_available(self, sample_questions):
        result = pick_next_question(sample_questions, [], {})
        assert result is not None
        assert isinstance(result, Question)

    def test_returns_none_when_all_asked(self, sample_questions):
        asked = [q.id for q in sample_questions]
        result = pick_next_question(sample_questions, asked, {})
        assert result is None

    def test_filters_out_asked_questions(self, sample_questions):
        asked = ["childhood_001", "childhood_002"]
        for _ in range(20):
            result = pick_next_question(sample_questions, asked, {})
            assert result is not None
            assert result.id not in asked

    def test_respects_selected_pack(self, sample_questions):
        for _ in range(20):
            result = pick_next_question(sample_questions, [], {}, selected_pack="school")
            assert result is not None
            assert result.pack == "school"

    def test_selected_pack_fallback_when_all_asked(self, sample_questions):
        """If all questions from selected pack are asked, pick from others."""
        asked = ["school_001"]
        result = pick_next_question(sample_questions, asked, {}, selected_pack="school")
        assert result is not None
        assert result.id != "school_001"

    def test_prefers_easy_over_medium(self, sample_questions):
        results = set()
        for _ in range(50):
            r = pick_next_question(sample_questions, [], {})
            results.add(r.id)
        assert "hardships_001" not in results or len(results) > 1

    def test_prefers_low_coverage_topics(self, sample_questions):
        coverage = {"home": 10, "childhood": 10, "games": 10}
        results = []
        for _ in range(30):
            r = pick_next_question(sample_questions, [], coverage)
            results.append(r.id)
        school_count = results.count("school_001")
        work_count = results.count("work_001")
        assert school_count + work_count > len(results) * 0.3

    def test_avoids_same_tags_as_last(self, sample_questions):
        results = []
        for _ in range(30):
            r = pick_next_question(
                sample_questions, [], {},
                last_tags=["home", "childhood"],
            )
            results.append(r.id)
        non_childhood = [r for r in results if r not in ("childhood_001", "childhood_002")]
        assert len(non_childhood) > len(results) * 0.3

    def test_empty_questions_list(self):
        result = pick_next_question([], [], {})
        assert result is None


class TestGetFollowup:
    def test_returns_first_followup(self, sample_questions):
        q = sample_questions[0]
        result = get_followup(q, 0)
        assert result == "Кто жил вместе с вами?"

    def test_returns_second_followup(self, sample_questions):
        q = sample_questions[0]
        result = get_followup(q, 1)
        assert result == "Тепло было?"

    def test_returns_none_for_out_of_range(self, sample_questions):
        q = sample_questions[0]
        result = get_followup(q, 99)
        assert result is None

    def test_returns_none_for_empty_followups(self):
        q = Question(id="test", pack="test", text="t", followups=[])
        result = get_followup(q)
        assert result is None
