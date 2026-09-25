"""Extract → clean → chunk. Pure functions, no database or AI."""

import pytest

from app.services.document_processing import (
    InvalidDocumentError,
    clean_text,
    extract_text,
    split_into_chunks,
)


def tiny_pdf(text: str) -> bytes:
    """Build a real one-page PDF containing `text` (no PDF library needed)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return out


# ---------- Extract ----------


def test_text_and_markdown_files() -> None:
    assert extract_text("notes.txt", b"Refunds take 5 days") == "Refunds take 5 days"
    assert extract_text("Guide.MD", b"# Title\n\nBody") == "# Title\n\nBody"


def test_real_pdf_text_is_extracted() -> None:
    assert "Refunds within 14 days" in extract_text("policy.pdf", tiny_pdf("Refunds within 14 days"))


@pytest.mark.parametrize(
    "filename, data, message",
    [
        ("virus.exe", b"MZ...", "Only"),
        ("fake.pdf", b"MZ this is really an exe", "not a real PDF"),
        ("broken.pdf", b"%PDF-1.4 garbage", "could not be read"),
        ("binary.txt", b"abc\x00def", "not a text file"),
        ("latin1.txt", "café".encode("latin-1"), "UTF-8"),
    ],
)
def test_bad_files_are_rejected(filename: str, data: bytes, message: str) -> None:
    with pytest.raises(InvalidDocumentError, match=message):
        extract_text(filename, data)


# ---------- Clean ----------


def test_clean_text() -> None:
    messy = "Title\r\n\r\n\r\n\r\nLine   one\t\twith  gaps   \nLine two\x07\n\n\n"

    assert clean_text(messy) == "Title\n\nLine one with gaps\nLine two"


# ---------- Chunk ----------


def test_short_text_is_one_chunk() -> None:
    assert split_into_chunks("One small paragraph.", size=800, overlap=150) == ["One small paragraph."]


def test_chunks_respect_the_size_and_never_cut_words() -> None:
    text = "\n\n".join(f"Paragraph {i}. " + "alpha beta gamma delta " * 20 for i in range(10))

    chunks = split_into_chunks(text, size=400, overlap=80)

    assert len(chunks) > 3
    assert all(len(chunk) <= 400 + 80 for chunk in chunks)  # size, plus at most the overlap
    words = set(text.split())
    assert all(set(chunk.split()) <= words for chunk in chunks)  # no half words


def test_neighbouring_chunks_overlap() -> None:
    text = "\n\n".join(f"Sentence number {i} is here." * 5 for i in range(10))

    chunks = split_into_chunks(text, size=300, overlap=60)

    for previous, current in zip(chunks, chunks[1:], strict=False):
        first_line = current.split("\n\n")[0]
        assert first_line in previous  # the start of each chunk repeats the end of the one before


def test_one_huge_paragraph_is_split() -> None:
    text = "word " * 1000  # one 5000-character paragraph

    chunks = split_into_chunks(text.strip(), size=500, overlap=50)

    assert len(chunks) >= 10
    assert all(len(chunk) <= 550 for chunk in chunks)


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValueError):
        split_into_chunks("text", size=100, overlap=100)
