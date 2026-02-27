from __future__ import annotations

from io import BytesIO
from pathlib import Path

from docx import Document as DocxDocument
from pypdf import PdfReader


TEXT_TYPES = {
    "text/plain",
    "text/markdown",
    "application/json",
}

PDF_TYPES = {"application/pdf"}

DOCX_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


def extract_text_from_upload(
    *,
    filename: str,
    content_type: str | None,
    raw: bytes,
) -> tuple[str, str]:
    """
    Returns (normalized_content_type, extracted_text).
    Raises ValueError for unsupported/invalid files.
    """
    name = filename or ""
    ext = Path(name).suffix.lower()
    ctype = (content_type or "").strip().lower()

    if ctype in TEXT_TYPES or ext in {".txt", ".md", ".json"}:
        text = raw.decode("utf-8", errors="ignore").strip()
        if not text:
            raise ValueError("Uploaded text file is empty.")
        return ("text/plain", text)

    if ctype in PDF_TYPES or ext == ".pdf":
        try:
            reader = PdfReader(BytesIO(raw))
            parts: list[str] = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                if page_text.strip():
                    parts.append(page_text.strip())
            text = "\n\n".join(parts).strip()
        except Exception as exc:
            raise ValueError(f"Could not parse PDF: {exc}") from exc
        if not text:
            raise ValueError("PDF contains no extractable text.")
        return ("application/pdf", text)

    if ctype in DOCX_TYPES or ext == ".docx":
        try:
            doc = DocxDocument(BytesIO(raw))
            lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
            text = "\n".join(lines).strip()
        except Exception as exc:
            raise ValueError(f"Could not parse DOCX: {exc}") from exc
        if not text:
            raise ValueError("DOCX contains no extractable text.")
        return (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            text,
        )

    raise ValueError(
        f"Unsupported file type: {content_type or '(unknown)'}; supported: txt, md, json, pdf, docx."
    )
