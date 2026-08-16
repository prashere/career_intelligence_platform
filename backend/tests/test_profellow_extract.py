"""ProFellow Jina markdown extraction."""

from app.ingestion.extract.heuristic import extract_from_jina_markdown

SAMPLE = """
# Knight-Hennessy Scholars Program

![Image 8: Organization](https://www.profellow.com/icon.organization.svg) Stanford University

![Image 9: Location](https://www.profellow.com/icon.location.svg) United States

![Image 10: Deadline](https://www.profellow.com/icon.deadline.svg) October 11, 2026

 The Knight-Hennessy Scholars Program is a fully funded graduate scholarship and leadership development program at Stanford University.

**Type:** Fellowship

## Create a free ProFellow account
"""


def test_extract_from_jina_markdown_profellow_shape():
    extracted = extract_from_jina_markdown(
        SAMPLE,
        "https://www.profellow.com/fellowship/knight-hennessy-scholars-fellowship/",
        {"deadline_patterns": [r"(?i)deadline[:\s]+([^<\n.]+)"]},
    )
    assert extracted.title == "Knight-Hennessy Scholars Program"
    assert extracted.institution == "Stanford University"
    assert extracted.deadline is not None
    assert "fully funded" in extracted.summary.lower()
