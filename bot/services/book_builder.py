from bot.db.models import Chapter, Memory


def compile_chapter(chapter: Chapter, memories: list[Memory]) -> str:
    """Compile a chapter from its approved memories into a readable text block."""
    if not memories:
        return ""

    lines = [f"# {chapter.title}\n"]
    if chapter.period_hint:
        lines.append(f"*{chapter.period_hint}*\n")
    lines.append("")

    for mem in memories:
        text = mem.edited_memoir_text or mem.cleaned_transcript or mem.raw_transcript or ""
        if mem.title:
            lines.append(f"## {mem.title}\n")
        lines.append(text)
        lines.append("\n---\n")

    return "\n".join(lines)


def compile_book(
    chapters: list[Chapter],
    memories_by_chapter: dict[int, list[Memory]],
    author_name: str = "",
) -> str:
    """Compile the entire book from all chapters."""
    lines = []

    if author_name:
        lines.append(f"# {author_name}\n")
        lines.append("## Книга воспоминаний\n\n---\n")

    for chapter in chapters:
        chapter_memories = memories_by_chapter.get(chapter.id, [])
        if chapter_memories:
            lines.append(compile_chapter(chapter, chapter_memories))
            lines.append("\n")

    return "\n".join(lines)
