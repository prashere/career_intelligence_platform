"""Extract plain text from CV uploads (PDF or TXT)."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader

MAX_CV_BYTES = 10 * 1024 * 1024  # 10 MB


def extract_text_from_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts)


def extract_text_from_cv_file(filename: str, data: bytes) -> str:
    if len(data) > MAX_CV_BYTES:
        raise ValueError(f"File too large (max {MAX_CV_BYTES // (1024 * 1024)} MB)")

    lower = filename.lower()
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf(data)
    elif lower.endswith(".txt"):
        text = data.decode("utf-8", errors="replace")
    else:
        raise ValueError("Unsupported file type. Upload a PDF or plain-text (.txt) CV.")

    cleaned = text.strip()
    if len(cleaned) < 50:
        raise ValueError(
            "Could not extract enough text from the file. "
            "Try a different PDF export or paste the CV text manually."
        )
    return cleaned
