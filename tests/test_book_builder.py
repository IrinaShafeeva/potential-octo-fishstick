from bot.db.models import Chapter, Memory
from bot.services.book_builder import compile_chapter, compile_book


def _make_chapter(id=1, title="Детство", period_hint=None):
    ch = Chapter.__new__(Chapter)
    ch.id = id
    ch.title = title
    ch.period_hint = period_hint
    return ch


def _make_memory(id=1, title="Дом", edited="Текст воспоминания", cleaned=None, raw=None):
    m = Memory.__new__(Memory)
    m.id = id
    m.title = title
    m.edited_memoir_text = edited
    m.cleaned_transcript = cleaned
    m.raw_transcript = raw
    return m


class TestCompileChapter:
    def test_empty_memories(self):
        ch = _make_chapter()
        assert compile_chapter(ch, []) == ""

    def test_single_memory(self):
        ch = _make_chapter(title="Детство")
        mem = _make_memory(title="Двор", edited="Мы играли во дворе.")
        result = compile_chapter(ch, [mem])
        assert "# Детство" in result
        assert "## Двор" in result
        assert "Мы играли во дворе." in result

    def test_includes_period_hint(self):
        ch = _make_chapter(title="Школа", period_hint="1960-1970")
        mem = _make_memory()
        result = compile_chapter(ch, [mem])
        assert "*1960-1970*" in result

    def test_multiple_memories(self):
        ch = _make_chapter()
        mems = [
            _make_memory(id=1, title="А", edited="Текст А"),
            _make_memory(id=2, title="Б", edited="Текст Б"),
        ]
        result = compile_chapter(ch, mems)
        assert "## А" in result
        assert "## Б" in result
        assert "---" in result

    def test_fallback_to_cleaned_transcript(self):
        ch = _make_chapter()
        mem = _make_memory(edited=None, cleaned="Очищенный текст")
        result = compile_chapter(ch, [mem])
        assert "Очищенный текст" in result

    def test_fallback_to_raw_transcript(self):
        ch = _make_chapter()
        mem = _make_memory(edited=None, cleaned=None, raw="Сырой текст")
        result = compile_chapter(ch, [mem])
        assert "Сырой текст" in result


class TestCompileBook:
    def test_empty_book(self):
        result = compile_book([], {})
        assert result == ""

    def test_book_with_author(self):
        ch = _make_chapter(id=1)
        mem = _make_memory()
        result = compile_book([ch], {1: [mem]}, author_name="Иван Иванович")
        assert "# Иван Иванович" in result
        assert "Книга воспоминаний" in result

    def test_skips_empty_chapters(self):
        ch1 = _make_chapter(id=1, title="Детство")
        ch2 = _make_chapter(id=2, title="Школа")
        mem = _make_memory()
        result = compile_book([ch1, ch2], {1: [mem], 2: []})
        assert "Детство" in result
        assert "Школа" not in result

    def test_multiple_chapters(self):
        ch1 = _make_chapter(id=1, title="Глава 1")
        ch2 = _make_chapter(id=2, title="Глава 2")
        result = compile_book(
            [ch1, ch2],
            {
                1: [_make_memory(id=1, title="А", edited="Текст А")],
                2: [_make_memory(id=2, title="Б", edited="Текст Б")],
            },
        )
        assert "Глава 1" in result
        assert "Глава 2" in result
