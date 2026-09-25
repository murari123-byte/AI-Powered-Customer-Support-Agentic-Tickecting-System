"""Turn an uploaded file into clean text, then into chunks. Pure functions: no database, no AI.

Why chunks? An embedding describes the meaning of ONE piece of text. A whole 10-page document
would get one blurry vector. Small chunks (a few paragraphs each) let search find the exact
part that answers a question, and keep the LLM's context short.
"""

import io
import re
from pathlib import PurePath

from pypdf import PdfReader
from pypdf.errors import PdfReadError

ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}
MAX_PDF_PAGES = 200


class InvalidDocumentError(Exception):
    """The file can't be used: wrong type, unreadable, or no text in it."""


# ---------- 1. Extract ----------


def extract_text(filename: str, data: bytes) -> str:
    """Get the text out of a .txt, .md or .pdf file. The file's CONTENT is checked, not just its name."""
    extension = PurePath(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidDocumentError(f"Only {', '.join(sorted(ALLOWED_EXTENSIONS))} files are allowed")

    if extension == ".pdf":
        if not data.startswith(b"%PDF-"):  # a renamed .exe or .zip would fail here
            raise InvalidDocumentError("The file is not a real PDF")
        try:
            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > MAX_PDF_PAGES:
                raise InvalidDocumentError(f"PDFs can have at most {MAX_PDF_PAGES} pages")
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except PdfReadError as exc:
            raise InvalidDocumentError("The PDF could not be read") from exc
        if not text.strip():
            raise InvalidDocumentError("No text found in the PDF (is it a scanned image?)")
        return text

    if b"\x00" in data:  # text files never contain null bytes; binary files usually do
        raise InvalidDocumentError("The file is not a text file")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidDocumentError("Text files must be UTF-8") from exc


# ---------- 2. Clean ----------


def clean_text(text: str) -> str:
    """Tidy whitespace so chunking works well: unify line endings, drop control characters,
    squeeze spaces, and keep at most one blank line between paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)  # control characters (keeps \n)
    text = re.sub(r"[  ]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------- 3. Chunk ----------


def _split_long_paragraph(paragraph: str, size: int) -> list[str]:
    """A paragraph longer than `size`: split at sentence ends, and at spaces if a sentence is still too long."""
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
        while len(sentence) > size:  # a huge "sentence": cut at the last space before the limit
            cut = sentence.rfind(" ", 0, size)
            cut = cut if cut > 0 else size
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if current and len(current) + 1 + len(sentence) > size:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _overlap_tail(chunk: str, overlap: int) -> str:
    """The last ~`overlap` characters of a chunk, starting at a word boundary."""
    if overlap <= 0 or len(chunk) <= overlap:
        return ""
    tail = chunk[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if space != -1 else tail


def split_into_chunks(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    """Split text into chunks of about `size` characters, never cutting in the middle of a word.

    - Paragraphs are kept together when they fit.
    - Each chunk starts with the last ~`overlap` characters of the previous one, so a fact that
      falls on a boundary is still found whole in at least one chunk.
    """
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    pieces = [piece for p in paragraphs for piece in (_split_long_paragraph(p, size) if len(p) > size else [p])]

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + 2 + len(piece) > size:
            chunks.append(current)
            tail = _overlap_tail(current, overlap)
            current = f"{tail}\n\n{piece}" if tail else piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        chunks.append(current)
    return chunks
