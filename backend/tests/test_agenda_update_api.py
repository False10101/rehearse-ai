from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from pptx import Presentation as Deck
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.api.v1 import presentations as api
from app.db.models import User, Presentation, PresentationAnalysis, Slide
from app.services import agenda_generator as generator
from app.services.agenda_layouts import PREVIEW_ITEMS


@compiles(JSONB, "sqlite")
def jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine("sqlite://")
    for model in (User, Presentation, PresentationAnalysis, Slide):
        model.__table__.create(engine)
    source = tmp_path / "deck.pptx"
    deck = Deck()
    deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = "Cover"
    generator.draw_agenda(deck.slides.add_slide(deck.slide_layouts[6]), PREVIEW_ITEMS,
                          "paired-sections", "violet", deck.slide_width, deck.slide_height)
    deck.slides.add_slide(deck.slide_layouts[0]).shapes.title.text = "Results"
    deck.save(source)
    def render(path, directory):
        images = {}
        for i in range(1, len(Deck(path).slides) + 1):
            images[i] = directory / f"slide-{i}.png"
            images[i].write_bytes(b"preview")
        return images
    monkeypatch.setattr(api, "render_slides_to_images", render)
    monkeypatch.setattr(api, "storage_path", lambda key: tmp_path / key)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        user = User(auth0_subject="agenda-test")
        session.add(user); session.flush()
        p = Presentation(user_id=user.id, title="Deck", original_filename="deck.pptx",
                         storage_key="deck.pptx", status="completed", slide_count=3)
        session.add(p); session.flush()
        for number in range(1, 4):
            content = {"num": number, "text": [{"t": "Source"}],
                       "img_context": "Original visual context", "vision_status": "completed"}
            if number == 2:
                content.update(generated_by="agenda", agenda_layout="paired-sections",
                               agenda_theme="violet", agenda_items=[x["title"] for x in PREVIEW_ITEMS])
            session.add(Slide(presentation_id=p.id, slide_number=number, extracted_content=content))
        analysis = PresentationAnalysis(presentation_id=p.id, model_id="test", prompt_version="test",
            status="completed", agenda_status="found", raw_output={"agenda_status": "found",
                "cohesion_feedback": "Slide 3 presents results.",
                "per_slide": [{"num": 1, "note": "Keep"}, {"num": 3, "note": "Keep"}]})
        session.add(analysis); session.commit()
        yield session, user, p, analysis, source


@pytest.mark.parametrize("action", ["design", "regenerate"])
def test_update_preserves_ids_other_content_feedback_and_slide_count(setup, monkeypatch, action):
    session, user, p, analysis, source = setup
    rows = list(session.scalars(select(Slide).order_by(Slide.slide_number)))
    ids = [r.id for r in rows]
    original_content = [deepcopy(r.extracted_content) for r in rows]
    original_feedback = deepcopy(analysis.raw_output)
    model = Mock(return_value=(PREVIEW_ITEMS[:4], 1)) if action == "regenerate" else Mock(
        side_effect=AssertionError("Design must not call AI"))
    monkeypatch.setattr(generator, "_items_from_model", model)
    for theme in ("forest", "ocean"):
        response = api.generate_agenda(p.id, api.GenerateAgendaRequest(
            layout="editorial-list", theme=theme, action=action, background="peach"), session, user)
        assert response.inserted_slide_number == 2
        assert p.slide_count == 3 and len(Deck(source).slides) == 3
        assert [r.id for r in session.scalars(select(Slide).order_by(Slide.slide_number))] == ids
        assert rows[0].extracted_content == original_content[0]
        assert rows[2].extracted_content == original_content[2]
        assert analysis.raw_output["per_slide"] == original_feedback["per_slide"]
        assert analysis.raw_output["cohesion_feedback"] == original_feedback["cohesion_feedback"]
        assert rows[1].extracted_content["agenda_theme"] == theme
        assert rows[1].extracted_content["agenda_background"] == "peach"
        assert analysis.raw_output["generated_agenda"]["background"] == "peach"
        assert str(Deck(source).slides[1].background.fill.fore_color.rgb) == "FFEADB"
        assert rows[1].extracted_content["agenda_sections"]
    assert model.call_count == (2 if action == "regenerate" else 0)


@pytest.mark.parametrize("action", ["create", "design", "regenerate"])
def test_original_agenda_cannot_be_created_over_or_updated(setup, action):
    session, user, p, analysis, source = setup
    agenda = session.scalar(select(Slide).where(Slide.slide_number == 2))
    agenda.extracted_content = {"num": 2, "title": "Original agenda"}
    session.commit()
    before = source.read_bytes()
    with pytest.raises(HTTPException) as error:
        api.generate_agenda(p.id, api.GenerateAgendaRequest(
            layout="editorial-list", theme="forest", action=action), session, user)
    assert error.value.status_code == 409
    assert source.read_bytes() == before
