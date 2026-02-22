from bot.keyboards.main_menu import main_menu_kb, onboarding_kb, BTN_RECORD, BTN_QUESTIONS
from bot.keyboards.inline_memory import memory_preview_kb, chapter_select_kb
from bot.keyboards.inline_question import pack_select_kb, question_actions_kb, followup_kb, PACKS_DISPLAY


class TestMainMenu:
    def test_main_menu_has_all_buttons(self):
        kb = main_menu_kb()
        texts = [btn.text for row in kb.keyboard for btn in row]
        assert BTN_RECORD in texts
        assert BTN_QUESTIONS in texts
        assert "📖 Моя книга" in texts
        assert "🧩 Структура глав" in texts
        assert "⭐ Подписка" in texts

    def test_main_menu_is_resized(self):
        kb = main_menu_kb()
        assert kb.resize_keyboard is True

    def test_onboarding_has_three_options(self):
        kb = onboarding_kb()
        texts = [btn.text for row in kb.keyboard for btn in row]
        assert len(texts) == 3
        assert "🎙 Начать говорить" in texts
        assert "🧠 Помочь вопросами" in texts

    def test_onboarding_is_one_time(self):
        kb = onboarding_kb()
        assert kb.one_time_keyboard is True


class TestInlineMemory:
    def test_preview_kb_has_all_actions(self):
        kb = memory_preview_kb(42)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "mem_save:42" in callbacks
        assert "mem_edit:42" in callbacks
        assert "mem_split:42" in callbacks
        assert "mem_move:42" in callbacks
        assert "mem_redo:42" in callbacks

    def test_chapter_select_has_chapters(self):
        chapters = [
            {"id": 1, "title": "Детство"},
            {"id": 2, "title": "Школа"},
        ]
        kb = chapter_select_kb(chapters, memory_id=10)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "mem_to_ch:10:1" in callbacks
        assert "mem_to_ch:10:2" in callbacks
        assert "mem_new_ch:10" in callbacks


class TestInlineQuestion:
    def test_pack_select_has_all_packs(self):
        kb = pack_select_kb()
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        for pack_id in PACKS_DISPLAY:
            assert f"pack:{pack_id}" in callbacks
        assert "pack:any" in callbacks

    def test_question_actions_has_all_buttons(self):
        kb = question_actions_kb(7)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "q_voice:7" in callbacks
        assert "q_text:7" in callbacks
        assert "q_next:7" in callbacks
        assert "q_pause:7" in callbacks

    def test_followup_kb_has_all_buttons(self):
        kb = followup_kb(3)
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        assert "q_voice:3" in callbacks
        assert "q_text:3" in callbacks
        assert "q_next:3" in callbacks
        assert "q_pause:3" in callbacks
