import asyncio
import io
import uuid
import zipfile
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from fastapi import HTTPException

from app.api.v1 import presentations, transcripts
from app.services.report_export import feedback_workbook


def test_workbook_preserves_saved_feedback_as_literal_text():
    analysis = {
        "summary": "A & B <details>",
        "per_slide": [
            {
                "num": 2,
                "slide_score": 6,
                "overload": True,
                "improvement_suggestions": ["=SUM(A1:A2)", "Fix café spelling"],
                "table_tips": [],
                "refs_found": [],
            }
        ],
    }
    with zipfile.ZipFile(io.BytesIO(feedback_workbook(analysis))) as archive:
        for name in archive.namelist():
            ElementTree.fromstring(archive.read(name))
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        assert not root.findall(".//s:f", ns)
        texts = [item.text for item in root.findall(".//s:t", ns)]
        assert "=SUM(A1:A2)\nFix café spelling" in texts


def test_transcript_export_uses_current_saved_text_and_slide_order(monkeypatch):
    presentation = SimpleNamespace(original_filename="Test.pptx")
    first, second = uuid.uuid4(), uuid.uuid4()
    slides = [
        SimpleNamespace(id=first, slide_number=1, title="Intro"),
        SimpleNamespace(id=second, slide_number=2, title="End"),
    ]
    session = SimpleNamespace(scalars=lambda query: SimpleNamespace(all=lambda: slides))
    transcript = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(transcripts, "owned_presentation", lambda *args: presentation)
    monkeypatch.setattr(transcripts, "_latest_by_slide", lambda *args: ({first: transcript}, {}))
    monkeypatch.setattr(
        transcripts,
        "_paragraphs",
        lambda *args: [
            SimpleNamespace(current_text="Edited café paragraph."),
            SimpleNamespace(current_text="Second paragraph."),
        ],
    )
    result = transcripts.export_transcript(uuid.uuid4(), session, SimpleNamespace(id=uuid.uuid4()))
    text = result.body.decode()
    assert "Edited café paragraph.\n\nSecond paragraph." in text
    assert text.index("Slide 1") < text.index("Slide 2")


def test_export_uses_ownership_check(monkeypatch):
    def deny(*args):
        raise HTTPException(status_code=404)

    monkeypatch.setattr(presentations, "owned_presentation", deny)
    monkeypatch.setattr(transcripts, "owned_presentation", deny)
    for endpoint in (presentations.export_presentation, transcripts.export_transcript):
        with pytest.raises(HTTPException) as error:
            endpoint(uuid.uuid4(), None, SimpleNamespace(id=uuid.uuid4()))
        assert error.value.status_code == 404


def test_presentation_export_keeps_current_deck_bytes(monkeypatch, tmp_path):
    source = tmp_path / "deck.pptx"
    source.write_bytes(b"current deck including agenda")
    presentation = SimpleNamespace(
        id=uuid.uuid4(), status="completed", storage_key="deck.pptx", original_filename="deck.pptx"
    )
    session = SimpleNamespace(scalar=lambda query: SimpleNamespace(raw_output={"per_slide": []}))
    monkeypatch.setattr(presentations, "owned_presentation", lambda *args: presentation)
    monkeypatch.setattr(presentations, "storage_path", lambda *args: source)
    result = presentations.export_presentation(
        presentation.id, session, SimpleNamespace(id=uuid.uuid4())
    )

    async def consume():
        return b"".join([part async for part in result.body_iterator])

    with zipfile.ZipFile(io.BytesIO(asyncio.run(consume()))) as archive:
        assert archive.read("deck.pptx") == source.read_bytes()
        assert "slide-feedback.xlsx" in archive.namelist()
