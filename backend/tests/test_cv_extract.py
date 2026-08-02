"""Tests for CV text extraction."""

from app.services.cv_extract import extract_text_from_cv_file


def test_extract_txt():
    data = b"Hello CV line one\nLine two with enough content for validation."
    text = extract_text_from_cv_file("resume.txt", data)
    assert "Hello CV" in text


def test_rejects_short_pdf(monkeypatch):
    def fake_pdf(_data: bytes) -> str:
        return "short"

    monkeypatch.setattr("app.services.cv_extract.extract_text_from_pdf", fake_pdf)
    try:
        extract_text_from_cv_file("cv.pdf", b"%PDF-fake")
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "enough text" in str(exc).lower()
