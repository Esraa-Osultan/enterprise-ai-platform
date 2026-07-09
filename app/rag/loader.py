"""
Turns a file on disk into plain text + a page map, so downstream chunking
can still say "this came from page 22" like the original pitch wanted.
"""

import os
from dataclasses import dataclass

import fitz  # PyMuPDF
from docx import Document as DocxDocument


@dataclass
class PageText:
    page_number: int  # 1-indexed, matches how a human would say "page 3"
    text: str


class UnsupportedFileType(Exception):
    pass


def load_document(file_path: str) -> list[PageText]:
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return _load_pdf(file_path)
    if ext == ".docx":
        return _load_docx(file_path)
    if ext in (".txt", ".md"):
        return _load_plain_text(file_path)

    raise UnsupportedFileType(f"'{ext}' files are not supported yet")


def _load_pdf(file_path: str) -> list[PageText]:
    pages = []
    with fitz.open(file_path) as pdf:
        for i, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if text:
                pages.append(PageText(page_number=i, text=text))
    return pages


def _load_docx(file_path: str) -> list[PageText]:
    # .docx has no fixed "pages" (that's a rendering concept), so we treat
    # the whole document as a single logical page for citation purposes.
    doc = DocxDocument(file_path)
    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return [PageText(page_number=1, text=text)] if text else []


def _load_plain_text(file_path: str) -> list[PageText]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read().strip()
    return [PageText(page_number=1, text=text)] if text else []
