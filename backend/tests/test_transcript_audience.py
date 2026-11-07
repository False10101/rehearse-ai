import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError

from app.api.v1.transcripts import GenerateAllRequest, GenerateSlideRequest
from app.services import transcript_enhancer as service


@pytest.mark.parametrize("level", ["beginner", "general", "specialist"])
def test_generation_prompt_uses_selected_audience(monkeypatch, level):
    prompts = []
    monkeypatch.setattr(
        service,
        "_request_json",
        lambda prompt, **kwargs: (
            prompts.append(prompt)
            or {
                "paragraphs": ["A supported spoken explanation."],
                "tone_check": {
                    "classification": "Informative",
                    "confidence": 0.9,
                    "rationale": "A neutral explanation.",
                },
            }
        ),
    )
    service.generate_script(
        {"text": "A supported idea"}, 75, "informative", "natural", audience_level=level
    )
    assert f"Audience level: {level}" in prompts[0]
    assert service.AUDIENCE_RULES[level] in prompts[0]
    assert "Target tone: informative" in prompts[0]


@pytest.mark.parametrize("level", ["beginner", "general", "specialist"])
def test_selection_prompt_uses_level_and_preserves_paragraphs(monkeypatch, level):
    prompts = []

    def request(prompt, **kwargs):
        prompts.append(prompt)
        return {"replacement_paragraphs": ["First explanation.", "Second explanation."]}

    monkeypatch.setattr(service, "_request_json", request)
    result = service.enhance_selection(
        {}, ["First.", "Second."], "informative", "formal", audience_level=level
    )
    assert len(result) == 2
    assert service.AUDIENCE_RULES[level] in prompts[0]
    assert "only within the selected text" in prompts[0]
    assert service.TONE_RULES["informative"] in prompts[0]
    assert service.STYLE_RULES["formal"] in prompts[0]


def test_requests_default_to_general_and_reject_unknown_level():
    assert GenerateSlideRequest(slide_number=1).audience_level == "general"
    assert (
        GenerateAllRequest(start_slide=1, end_slide=3, audience_level="beginner").audience_level
        == "beginner"
    )
    with pytest.raises(ValidationError):
        GenerateSlideRequest(slide_number=1, audience_level="pitch")


@pytest.mark.parametrize("already_present", [False, True])
def test_audience_migration_handles_existing_and_fresh_schemas(already_present):
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/20261010_14_transcript_audience_level.py"
    )
    spec = importlib.util.spec_from_file_location("audience_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        column = ", target_audience_level VARCHAR(32)" if already_present else ""
        connection.exec_driver_sql(
            f"CREATE TABLE presentation_transcripts (id INTEGER PRIMARY KEY{column})"
        )
        connection.exec_driver_sql("INSERT INTO presentation_transcripts (id) VALUES (1)")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.upgrade()
        assert "target_audience_level" in {
            item["name"] for item in sa.inspect(connection).get_columns("presentation_transcripts")
        }
        assert connection.exec_driver_sql(
            "SELECT id, target_audience_level FROM presentation_transcripts"
        ).one() == (1, None)


def test_selection_prompt_distinguishes_fragment_from_new_paragraph(monkeypatch):
    prompts = []

    def request(prompt, **kwargs):
        prompts.append(prompt)
        return {
            "replacement_paragraphs": [
                "a shorter wait.",
                "Because allocation varied, causality remains uncertain",
            ]
        }

    monkeypatch.setattr(service, "_request_json", request)
    result = service.enhance_selection(
        {},
        ["a lower wait.", "because allocation varied, causality remains uncertain"],
        "informative",
        "formal",
        surrounding_text={"before": "We observed ", "after": ". Next steps follow."},
        selection_boundaries={
            "first_part_starts_paragraph": False,
            "last_part_ends_paragraph": False,
        },
    )
    assert '"first_part_starts_paragraph": false' in prompts[0]
    assert "Every subsequent part starts a new paragraph" in prompts[0]
    assert result[0] == "a shorter wait."
    assert result[1] == "Because allocation varied, causality remains uncertain"
