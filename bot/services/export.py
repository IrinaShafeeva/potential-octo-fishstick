import logging
from pathlib import Path

from fpdf import FPDF

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).parent.parent / "fonts"


class MemoirPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

        font_path = FONTS_DIR / "DejaVuSans.ttf"
        font_bold_path = FONTS_DIR / "DejaVuSans-Bold.ttf"
        if font_path.exists():
            self.add_font("DejaVu", "", str(font_path), uni=True)
            if font_bold_path.exists():
                self.add_font("DejaVu", "B", str(font_bold_path), uni=True)
            self._font_family = "DejaVu"
        else:
            self._font_family = "Helvetica"

    def header(self):
        self.set_font(self._font_family, "B", 10)
        self.set_text_color(150, 150, 150)
        self.cell(0, 8, "Книга воспоминаний", align="R", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font(self._font_family, "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"— {self.page_no()} —", align="C")

    def chapter_title(self, title: str):
        self.set_font(self._font_family, "B", 16)
        self.set_text_color(30, 30, 30)
        self.ln(10)
        self.multi_cell(0, 10, title)
        self.ln(5)

    def memory_title(self, title: str):
        self.set_font(self._font_family, "B", 12)
        self.set_text_color(60, 60, 60)
        self.ln(5)
        self.multi_cell(0, 8, title)
        self.ln(3)

    def memory_body(self, text: str):
        self.set_font(self._font_family, "", 11)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 7, text)
        self.ln(3)

    def separator(self):
        self.set_draw_color(200, 200, 200)
        y = self.get_y()
        self.line(self.l_margin + 30, y, self.w - self.r_margin - 30, y)
        self.ln(5)


async def export_book_pdf(
    chapters_data: list[dict],
    author_name: str = "",
    user_id: int = 0,
) -> bytes | None:
    """Export book to PDF. Returns PDF bytes (no disk I/O).

    chapters_data: [{"title": str, "period_hint": str, "memories": [{"title": str, "text": str}]}]
    """
    pdf = MemoirPDF()

    pdf.add_page()
    pdf.set_font(pdf._font_family, "B", 24)
    pdf.set_text_color(30, 30, 30)
    pdf.ln(60)
    if author_name:
        pdf.multi_cell(0, 15, author_name, align="C")
        pdf.ln(5)
    pdf.set_font(pdf._font_family, "", 16)
    pdf.multi_cell(0, 10, "Книга воспоминаний", align="C")

    for chapter in chapters_data:
        if not chapter.get("memories"):
            continue
        pdf.add_page()
        pdf.chapter_title(chapter["title"])

        for i, mem in enumerate(chapter["memories"]):
            if mem.get("title"):
                pdf.memory_title(mem["title"])
            pdf.memory_body(mem.get("text", ""))
            if i < len(chapter["memories"]) - 1:
                pdf.separator()

    try:
        pdf_bytes = pdf.output()
        logger.info("PDF generated for user_id=%d (%d bytes)", user_id, len(pdf_bytes))
        return bytes(pdf_bytes)
    except Exception as e:
        logger.error("PDF export error: %s", e, exc_info=True)
        return None
