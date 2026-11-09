"""Exercise preview/accept/history against real transactions without provider calls."""

import uuid
from datetime import UTC
from threading import Barrier, Event, Lock, get_ident
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1 import transcripts as api
from app.db.models import (
    Job,
    Presentation,
    PresentationTranscript,
    Slide,
    SlideTranscript,
    SlideVocabularyUpgrade,
    TranscriptComplexTerm,
    TranscriptParagraph,
    TranscriptRevision,
    TranscriptVersion,
    User,
)


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(transcript_generation_workers=4)
    )
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    tables = [
        User,
        Job,
        Presentation,
        Slide,
        PresentationTranscript,
        SlideTranscript,
        TranscriptParagraph,
        TranscriptRevision,
        TranscriptVersion,
        TranscriptComplexTerm,
        SlideVocabularyUpgrade,
    ]
    for model in tables:
        model.__table__.create(engine)
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        user = User(auth0_subject="review-test")
        session.add(user)
        session.flush()
        presentation = Presentation(
            user_id=user.id, title="Test", original_filename="test.pptx", status="completed"
        )
        session.add(presentation)
        session.flush()
        slide = Slide(
            presentation_id=presentation.id,
            slide_number=1,
            extracted_content={"text": "Manage team tasks"},
        )
        parent = PresentationTranscript(
            presentation_id=presentation.id,
            mode="human-write",
            model_id="test",
            prompt_version="test",
        )
        session.add_all([slide, parent])
        session.flush()
        transcript = SlideTranscript(presentation_transcript_id=parent.id, slide_id=slide.id)
        session.add(transcript)
        session.flush()
        parts = [
            TranscriptParagraph(
                slide_transcript_id=transcript.id, position=i + 1, current_text=text
            )
            for i, text in enumerate(
                ["Prefix hey team suffix", "Second paragraph.", "Unselected paragraph."]
            )
        ]
        session.add_all(parts)
        session.commit()
        monkeypatch.setattr(
            api, "enhance_selection", lambda *_a, **_k: ["Good morning", "A second explanation."]
        )
        monkeypatch.setattr(
            api,
            "analyze_script",
            lambda *_a, **_k: {
                "complex_terms": [],
                "vocabulary_upgrades": [],
                "tone_check": {"classification": "Informative"},
            },
        )
        yield SimpleNamespace(
            session=session,
            user=user,
            presentation=presentation,
            slide=slide,
            transcript=transcript,
            parts=parts,
        )
    engine.dispose()


def request(ctx, **kwargs):
    return api.EnhanceSelectionRequest(
        slide_transcript_id=ctx.transcript.id,
        base_revision=1,
        start={"paragraph_id": ctx.parts[0].id, "offset": 7},
        end={"paragraph_id": ctx.parts[1].id, "offset": len(ctx.parts[1].current_text)},
        tone="informative",
        style="formal",
        audience_level="general",
        **kwargs,
    )


def preview(ctx, req=None):
    return api.preview_transcript_selection(
        ctx.presentation.id, req or request(ctx), ctx.session, ctx.user
    )


def accept(ctx, req=None, replacements=None):
    req = req or request(ctx)
    return api.accept_transcript_selection(
        ctx.presentation.id,
        api.AcceptEnhancementRequest(
            **req.model_dump(),
            replacement_paragraphs=replacements or ["Good morning", "A second explanation."],
        ),
        ctx.session,
        ctx.user,
    )


def test_preview_does_not_save_and_cancel_needs_no_request(setup):
    c = setup
    result = preview(c)
    assert result.before == ["hey team suffix", "Second paragraph."]
    assert result.after == ["Good morning", "A second explanation."]
    c.session.expire_all()
    assert c.transcript.revision == 1
    assert c.parts[0].current_text == "Prefix hey team suffix"
    assert c.session.scalars(select(TranscriptRevision)).all() == []


def test_accept_saves_exact_preview_once_without_generating_again(setup, monkeypatch):
    c = setup
    result = preview(c)
    monkeypatch.setattr(
        api, "enhance_selection", lambda *_a, **_k: pytest.fail("Accept called model")
    )
    updated = accept(c, replacements=result.after)
    assert updated.revision == 2
    assert [p.current for p in updated.paragraphs] == [
        "Prefix Good morning",
        "A second explanation.",
        "Unselected paragraph.",
    ]
    history = api.transcript_selection_history(c.presentation.id, 1, c.session, c.user)
    assert len(history) == 1
    assert history[0].before == "hey team suffix\n\nSecond paragraph."
    assert history[0].after == "Good morning\n\nA second explanation."
    assert history[0].style == "formal"
    with pytest.raises(HTTPException) as error:
        accept(c)
    assert error.value.status_code == 409


def test_accept_rejects_stale_preview(setup):
    c = setup
    preview(c)
    c.transcript.revision = 2
    c.session.commit()
    with pytest.raises(HTTPException) as error:
        accept(c)
    assert error.value.status_code == 409
    assert c.parts[0].current_text == "Prefix hey team suffix"


def test_preview_and_history_require_ownership(setup):
    c = setup
    other = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        api.preview_transcript_selection(c.presentation.id, request(c), c.session, other)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException):
        api.transcript_selection_history(c.presentation.id, 1, c.session, other)


def test_paragraph_count_and_unknown_ids_rejected(setup):
    c = setup
    with pytest.raises(HTTPException) as error:
        accept(c, replacements=["Only one paragraph"])
    assert error.value.status_code == 422
    req = request(c)
    req.start.paragraph_id = uuid.uuid4()
    with pytest.raises(HTTPException):
        preview(c, req)


def test_identical_suggestion_is_marked_unchanged(setup, monkeypatch):
    monkeypatch.setattr(api, "enhance_selection", lambda _slide, parts, *_a, **_k: parts)
    assert preview(setup).changed is False


def test_generation_saves_speech_and_feedback_from_one_provider_response(setup, monkeypatch):
    from app.services import transcript_enhancer

    c = setup
    calls = []

    def request(prompt, **kwargs):
        calls.append(prompt)
        assert kwargs["system_prompt"] == transcript_enhancer.TRANSCRIPT_SYSTEM_PROMPT
        return {
            "paragraphs": ["Our SME uses task ownership to coordinate work."],
            "complex_terms": [
                {
                    "term": "SME",
                    "definition": "A small or medium-sized enterprise.",
                    "pronunciation": "ess em ee",
                }
            ],
            "tone_check": {
                "classification": "Informative",
                "confidence": 0.9,
                "rationale": "The speaker communicates the subject neutrally.",
            },
            "vocabulary_upgrades": [],
        }

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    result = api.generate_slide_transcript(
        c.presentation.id, api.GenerateSlideRequest(slide_number=1), c.session, c.user
    )
    assert len(calls) == 1
    assert [p.current for p in result.paragraphs] == [
        "Our SME uses task ownership to coordinate work."
    ]
    assert [t.term for t in result.complex_terms] == ["SME"]
    assert result.tone_check.classification == "Informative"
    assert result.coaching_analysis_available is True
    # Generation creates a new version; it does not rewrite the previous human script.
    assert [p.current_text for p in c.parts] == [
        "Prefix hey team suffix",
        "Second paragraph.",
        "Unselected paragraph.",
    ]


def test_history_survives_manual_deletion_of_all_original_paragraphs(setup):
    c = setup
    accept(c)
    api.save_transcript_script(
        c.presentation.id,
        1,
        api.SaveScriptRequest(
            slide_transcript_id=c.transcript.id,
            base_revision=2,
            paragraphs=[api.SaveParagraph(text="")],
        ),
        c.session,
        c.user,
    )
    history = api.transcript_selection_history(c.presentation.id, 1, c.session, c.user)
    assert len(history) == 1
    assert history[0].before == "hey team suffix\n\nSecond paragraph."
    assert [p.current_text for p in api._paragraphs(c.session, c.transcript.id)] == [""]


def test_analysis_failure_does_not_lose_accepted_text(setup, monkeypatch):
    def fail(*_a, **_k):
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(api, "analyze_script", fail)
    result = accept(setup)
    assert result.revision == 2
    assert result.paragraphs[0].current == "Prefix Good morning"
    assert result.coaching_analysis_available is False


def test_preview_cannot_replace_a_newer_generated_script(setup):
    from datetime import datetime, timedelta

    c = setup
    req = request(c)
    preview(c, req)
    newer = SlideTranscript(
        presentation_transcript_id=c.transcript.presentation_transcript_id,
        slide_id=c.slide.id,
        revision=2,
        updated_at=datetime.now(UTC) + timedelta(seconds=5),
    )
    # A generation creates a new parent run as well as a new slide transcript.
    parent = PresentationTranscript(
        presentation_id=c.presentation.id, mode="ai-gen", model_id="test", prompt_version="test"
    )
    c.session.add(parent)
    c.session.flush()
    newer.presentation_transcript_id = parent.id
    c.session.add(newer)
    c.session.commit()
    with pytest.raises(HTTPException) as error:
        accept(c, req)
    assert error.value.status_code == 409
    assert c.parts[0].current_text == "Prefix hey team suffix"


def test_selection_passes_exact_untouched_context_to_model(setup, monkeypatch):
    c = setup
    captured = {}

    def enhance(_slide, parts, *_args, **kwargs):
        captured.update(kwargs)
        return parts

    monkeypatch.setattr(api, "enhance_selection", enhance)
    req = api.EnhanceSelectionRequest(
        slide_transcript_id=c.transcript.id,
        base_revision=1,
        start={"paragraph_id": c.parts[0].id, "offset": 7},
        end={"paragraph_id": c.parts[0].id, "offset": 15},
    )
    result = preview(c, req)
    assert result.before == ["hey team"]
    assert captured["selection_boundaries"] == {
        "first_part_starts_paragraph": False,
        "last_part_ends_paragraph": False,
    }
    assert captured["surrounding_text"]["before"] == "Prefix "
    assert captured["surrounding_text"]["after"] == (
        " suffix\n\nSecond paragraph.\n\nUnselected paragraph."
    )
    assert c.parts[0].current_text == "Prefix hey team suffix"


def test_selection_passes_complete_paragraph_boundaries(setup, monkeypatch):
    c = setup
    captured = {}

    def enhance(_slide, parts, *_args, **kwargs):
        captured.update(kwargs)
        return parts

    monkeypatch.setattr(api, "enhance_selection", enhance)
    req = api.EnhanceSelectionRequest(
        slide_transcript_id=c.transcript.id,
        base_revision=1,
        start={"paragraph_id": c.parts[0].id, "offset": 0},
        end={"paragraph_id": c.parts[1].id, "offset": len(c.parts[1].current_text)},
    )
    result = preview(c, req)
    assert len(result.before) == 2
    assert captured["selection_boundaries"] == {
        "first_part_starts_paragraph": True,
        "last_part_ends_paragraph": True,
    }
    assert [p.current_text for p in c.parts] == [
        "Prefix hey team suffix",
        "Second paragraph.",
        "Unselected paragraph.",
    ]


def test_neighbor_context_uses_nearest_saved_scripts_and_skips_current(setup):
    c = setup
    current = Slide(
        presentation_id=c.presentation.id,
        slide_number=2,
        title="Second",
        extracted_content={"text": []},
    )
    future = Slide(
        presentation_id=c.presentation.id,
        slide_number=3,
        title="Third",
        extracted_content={"text": []},
    )
    c.session.add_all([current, future])
    c.session.flush()
    parent = c.session.get(PresentationTranscript, c.transcript.presentation_transcript_id)
    st = SlideTranscript(presentation_transcript_id=parent.id, slide_id=future.id)
    c.session.add(st)
    c.session.flush()
    c.session.add(
        TranscriptParagraph(
            slide_transcript_id=st.id, position=1, current_text="A later conclusion."
        )
    )
    c.session.flush()
    contexts = api._neighboring_script_context(c.session, c.presentation, current)
    assert [item["slide_number"] for item in contexts] == [1, 3]
    assert "Prefix hey team suffix" in contexts[0]["script"]
    assert contexts[1]["script"] == "A later conclusion."


def test_bulk_generates_in_parallel_with_saved_context_and_serial_saves(setup, monkeypatch):
    c = setup
    for num in [2, 3]:
        c.session.add(
            Slide(
                presentation_id=c.presentation.id,
                slide_number=num,
                title=f"Slide {num}",
                extracted_content={"num": num, "text": []},
            )
        )
    job = Job(
        user_id=c.user.id,
        job_type="transcript_generate_all",
        target_type="presentation",
        target_id=c.presentation.id,
    )
    c.session.add(job)
    c.session.commit()
    original_id = c.parts[0].id
    job_id = job.id
    calls = []
    barrier = Barrier(2)
    first_saved = Event()
    main_thread = get_ident()
    written = []
    progress = []
    save = api._save_ai_slide_transcript

    def generate(slide, *_args, **kwargs):
        assert get_ident() != main_thread
        calls.append((slide["num"], kwargs["neighboring_scripts"]))
        barrier.wait(timeout=3)  # A serial implementation cannot pass this barrier.
        if slide["num"] == 2:
            assert first_saved.wait(timeout=3)
        return {
            "paragraphs": [f"New script for slide {slide['num']}."],
            "tone_check": {"classification": "Informative"},
        }

    def save_result(session, presentation, slide, *args):
        assert get_ident() == main_thread  # No database work on provider threads.
        result = save(session, presentation, slide, *args)
        written.append(slide.slide_number)
        if slide.slide_number == 3:
            first_saved.set()
        return result

    event.listen(
        c.session,
        "after_commit",
        lambda _session: progress.append(job.__dict__.get("progress_percent")),
    )
    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "_save_ai_slide_transcript", save_result)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 3)
    assert sorted(num for num, _ in calls) == [2, 3]
    assert all(context[0]["slide_number"] == 1 for _, context in calls)
    assert all("Prefix hey team suffix" in context[0]["script"] for _, context in calls)
    assert written == [3, 2]  # Results save as they finish, not in source order.
    assert 33 in progress and 67 in progress and progress[-1] == 100
    assert c.session.get(TranscriptParagraph, original_id).current_text == "Prefix hey team suffix"
    assert c.session.get(Job, job_id).status == "completed"


def test_bulk_failure_does_not_multiply_generation_attempts_or_erase_existing_script(
    setup, monkeypatch
):
    c = setup
    c.session.add(
        Slide(
            presentation_id=c.presentation.id,
            slide_number=2,
            title="Empty slide",
            extracted_content={"num": 2, "text": []},
        )
    )
    job = Job(
        user_id=c.user.id,
        job_type="transcript_generate_all",
        target_type="presentation",
        target_id=c.presentation.id,
    )
    c.session.add(job)
    c.session.commit()
    job_id, original_id = job.id, c.parts[0].id
    calls = []

    def failed(slide, *args, **kwargs):
        calls.append(slide["num"])
        raise ValueError("Invalid provider response")

    monkeypatch.setattr(api, "generate_script", failed)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 2)
    assert calls == [2]
    assert c.session.get(Job, job_id).status == "failed"
    assert c.session.get(TranscriptParagraph, original_id).current_text == "Prefix hey team suffix"


def _prepare_bulk_case(c, numbers):
    for number in numbers:
        c.session.add(
            Slide(
                presentation_id=c.presentation.id,
                slide_number=number,
                extracted_content={"num": number, "text": []},
            )
        )
    job = Job(
        user_id=c.user.id,
        job_type="transcript_generate_all",
        target_type="presentation",
        target_id=c.presentation.id,
    )
    c.session.add(job)
    c.session.commit()
    return job.id


def test_parallel_bulk_saves_other_successes_when_one_slide_fails(setup, monkeypatch):
    c = setup
    job_id = _prepare_bulk_case(c, [2, 3])
    original_id = c.parts[0].id
    calls = []
    barrier = Barrier(2)

    def generate(slide, **kwargs):
        calls.append(slide["num"])
        barrier.wait(timeout=3)
        if slide["num"] == 2:
            raise ValueError("Invalid provider response")
        return {"paragraphs": ["The successful third script."]}

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 3)
    assert sorted(calls) == [2, 3]
    job = c.session.get(Job, job_id)
    assert job.status == "failed" and job.error_code == "ValueError"
    latest, _ = api._latest_by_slide(c.session, c.presentation.id)
    slides = list(
        c.session.scalars(select(Slide).where(Slide.presentation_id == c.presentation.id))
    )
    ids = {slide.slide_number: slide.id for slide in slides}
    assert ids[2] not in latest
    assert [p.current_text for p in api._paragraphs(c.session, latest[ids[3]].id)] == [
        "The successful third script."
    ]
    assert c.session.get(TranscriptParagraph, original_id).current_text == "Prefix hey team suffix"


def test_parallel_bulk_only_generates_empty_slides_in_selected_range(setup, monkeypatch):
    c = setup
    job_id = _prepare_bulk_case(c, [2, 3, 4])
    second = c.session.scalar(
        select(Slide).where(Slide.presentation_id == c.presentation.id, Slide.slide_number == 2)
    )
    api._create_human_draft(c.session, c.presentation, second)
    c.session.commit()
    calls = []

    def generate(slide, **kwargs):
        calls.append(slide["num"])
        return {"paragraphs": [f"Script {slide['num']}."]}

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 3)
    assert sorted(calls) == [2, 3]
    assert c.session.get(Job, job_id).status == "completed"
    fourth = c.session.scalar(
        select(Slide).where(Slide.presentation_id == c.presentation.id, Slide.slide_number == 4)
    )
    latest, _ = api._latest_by_slide(c.session, c.presentation.id)
    assert fourth.id not in latest


def test_parallel_bulk_preserves_text_saved_while_provider_was_running(setup, monkeypatch):
    c = setup
    presentation_id = c.presentation.id
    job_id = _prepare_bulk_case(c, [2])
    request_ran = Event()
    inserted = False
    latest = api._latest_by_slide

    def generate(slide, **kwargs):
        request_ran.set()
        return {"paragraphs": ["The late AI result must not overwrite the edit."]}

    def simulate_saved_edit(session, presentation_id):
        nonlocal inserted
        if request_ran.is_set() and not inserted:
            inserted = True
            slide = session.scalar(
                select(Slide).where(
                    Slide.presentation_id == presentation_id, Slide.slide_number == 2
                )
            )
            human = api._create_human_draft(session, c.presentation, slide)
            session.flush()
            api._paragraphs(session, human.id)[0].current_text = "Written while generation ran."
            session.flush()
        return latest(session, presentation_id)

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "_latest_by_slide", simulate_saved_edit)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 2)
    slide = c.session.scalar(
        select(Slide).where(Slide.presentation_id == presentation_id, Slide.slide_number == 2)
    )
    written, _ = latest(c.session, presentation_id)
    assert [p.current_text for p in api._paragraphs(c.session, written[slide.id].id)] == [
        "Written while generation ran."
    ]
    assert c.session.get(Job, job_id).status == "completed"


def test_parallel_bulk_respects_concurrency_limit(setup, monkeypatch):
    c = setup
    job_id = _prepare_bulk_case(c, range(2, 8))
    monkeypatch.setattr(
        api, "get_settings", lambda: SimpleNamespace(transcript_generation_workers=2)
    )
    barrier = Barrier(2)
    lock = Lock()
    active = 0
    peak = 0
    calls = []

    def generate(slide, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append(slide["num"])
        barrier.wait(timeout=3)
        with lock:
            active -= 1
        return {"paragraphs": [f"Slide {slide['num']} script."]}

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 7)
    assert peak == 2 and sorted(calls) == list(range(2, 8))
    assert c.session.get(Job, job_id).status == "completed"


def test_bulk_with_no_empty_slides_finishes_without_provider_requests(setup, monkeypatch):
    c = setup
    job_id = _prepare_bulk_case(c, [])

    def unexpected(*args, **kwargs):
        pytest.fail("An existing script must not trigger generation")

    monkeypatch.setattr(api, "generate_script", unexpected)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(c.presentation.id, 75, "informative", "natural", 1, 1)
    job = c.session.get(Job, job_id)
    assert job.status == "completed" and job.progress_percent == 100


@pytest.mark.parametrize(
    "before,after,expected",
    [
        ("AI wording stays.", "AI wording stays.", []),
        ("AI wording stays.", "AI wording stays. Human words here.", ["Human words here."]),
        ("A weak point.", "A stronger point.", ["stronger"]),
        ("Delete these words.", "", []),
        ("", "A human draft.", ["A human draft."]),
    ],
)
def test_vocabulary_diff_does_not_include_untouched_words(before, after, expected):
    assert api._changed_words(before, after) == expected


def test_manual_save_scopes_vocabulary_and_reload_keeps_only_human_suggestions(setup, monkeypatch):
    from app.services import transcript_enhancer as service

    c = setup
    captures = []
    monkeypatch.setattr(api, "analyze_script", service.analyze_script)

    def feedback(prompt, **kwargs):
        captures.append(prompt)
        return {
            "tone_check": {
                "classification": "Informative",
                "confidence": 0.9,
                "rationale": "Current tone.",
            },
            "complex_terms": [],
            "vocabulary_upgrades": [
                {
                    "original": "Second paragraph",
                    "suggested": "Other wording",
                    "reason": "Untouched words.",
                },
                {
                    "original": "kinda messy",
                    "suggested": "unclear",
                    "reason": "Clearer human wording.",
                },
            ],
        }

    monkeypatch.setattr(service, "_request_json", feedback)
    result = api.save_transcript_script(
        c.presentation.id,
        1,
        api.SaveScriptRequest(
            slide_transcript_id=c.transcript.id,
            base_revision=1,
            paragraphs=[
                api.SaveParagraph(
                    id=p.id, text=p.current_text + (" A kinda messy explanation." if i == 0 else "")
                )
                for i, p in enumerate(c.parts)
            ],
        ),
        c.session,
        c.user,
    )
    assert result.paragraphs[1].current == "Second paragraph."
    assert [v.original for v in result.vocabulary_upgrades] == ["kinda messy"]
    scope = (
        captures[0]
        .split("HUMAN CHANGES (the only text eligible for vocabulary upgrades):\n")[1]
        .split("\n\nTRANSCRIPT:")[0]
    )
    assert "A kinda messy explanation." in scope and "Second paragraph" not in scope
    reloaded = api._response_for_slide(
        c.session, c.slide, c.transcript, "human-enhance", c.presentation
    )
    assert [v.original for v in reloaded.vocabulary_upgrades] == ["kinda messy"]
    # Saving again without changing text clears suggestions; nothing new is human-authored.
    again = api.save_transcript_script(
        c.presentation.id,
        1,
        api.SaveScriptRequest(
            slide_transcript_id=c.transcript.id,
            base_revision=2,
            paragraphs=[
                api.SaveParagraph(id=p.id, text=p.current_text)
                for p in api._paragraphs(c.session, c.transcript.id)
            ],
        ),
        c.session,
        c.user,
    )
    assert again.vocabulary_upgrades == []


def test_ai_generation_and_enhancement_never_persist_vocabulary_self_review(setup, monkeypatch):
    c = setup
    bad = {"original": "Good morning", "suggested": "Hello", "reason": "AI self-review."}
    monkeypatch.setattr(
        api,
        "analyze_script",
        lambda *a, **kw: {
            "tone_check": {"classification": "Informative"},
            "complex_terms": [],
            "vocabulary_upgrades": [bad],
        },
    )
    result = accept(c)
    assert result.vocabulary_upgrades == []
    assert list(c.session.scalars(select(SlideVocabularyUpgrade))) == []
    generated = api._save_ai_slide_transcript(
        c.session,
        c.presentation,
        c.slide,
        {
            "paragraphs": ["Good morning"],
            "complex_terms": [],
            "vocabulary_upgrades": [bad],
            "tone_check": {"classification": "Informative"},
        },
        75,
        "informative",
        "natural",
        "general",
    )
    c.session.commit()
    assert (
        api._response_for_slide(
            c.session, c.slide, generated, "ai-gen", c.presentation
        ).vocabulary_upgrades
        == []
    )
    assert list(c.session.scalars(select(SlideVocabularyUpgrade))) == []


def test_legacy_unscoped_vocabulary_is_hidden_on_reload(setup):
    c = setup
    api._apply_analysis(
        c.session,
        c.transcript,
        {
            "vocabulary_upgrades": [
                {
                    "original": "Second paragraph",
                    "suggested": "Another paragraph",
                    "reason": "Old self-review.",
                }
            ],
        },
    )
    c.session.add(
        TranscriptRevision(
            slide_transcript_id=c.transcript.id,
            base_revision=1,
            result_revision=2,
            start_paragraph_id=c.parts[0].id,
            start_offset=0,
            end_paragraph_id=c.parts[-1].id,
            end_offset=len(c.parts[-1].current_text),
            replacement_text="Legacy raw text, without human-change scope",
            source="human-edit",
        )
    )
    c.session.commit()
    assert (
        api._response_for_slide(
            c.session, c.slide, c.transcript, "human-enhance", c.presentation
        ).vocabulary_upgrades
        == []
    )


def versions(c):
    return api.transcript_versions(c.presentation.id, c.slide.slide_number, c.session, c.user)


def restore(c, version_id, *, transcript=None, revision=None):
    current = transcript or c.transcript
    return api.restore_transcript_version(
        c.presentation.id,
        c.slide.slide_number,
        version_id,
        api.RestoreVersionRequest(
            slide_transcript_id=current.id, base_revision=revision or current.revision
        ),
        c.session,
        c.user,
    )


def test_full_versions_capture_selection_and_untouched_paragraphs(setup):
    c = setup
    original = [p.current_text for p in c.parts]
    before_count = len(list(c.session.scalars(select(TranscriptVersion))))
    preview(c)
    assert len(list(c.session.scalars(select(TranscriptVersion)))) == before_count
    result = accept(c)
    history = versions(c)
    assert [v.change_type for v in history] == ["enhanced", "saved"]
    assert history[0].paragraphs == [p.current for p in result.paragraphs]
    assert history[0].paragraphs[-1] == "Unselected paragraph."
    assert history[1].paragraphs == original
    assert history[0].settings["tone"] == "informative"
    assert history[0].settings["style"] == "formal"
    assert history[0].is_current and not history[1].is_current


def test_manual_edit_snapshots_survive_paragraph_removal_and_empty_save(setup):
    c = setup
    original = [p.current_text for p in c.parts]
    saved = api.save_transcript_script(
        c.presentation.id,
        1,
        api.SaveScriptRequest(
            slide_transcript_id=c.transcript.id,
            base_revision=1,
            paragraphs=[
                {"id": c.parts[0].id, "text": "A replacement."},
                {"text": "New final paragraph."},
            ],
        ),
        c.session,
        c.user,
    )
    empty = api.save_transcript_script(
        c.presentation.id,
        1,
        api.SaveScriptRequest(
            slide_transcript_id=c.transcript.id,
            base_revision=saved.revision,
            paragraphs=[{"text": ""}],
        ),
        c.session,
        c.user,
    )
    history = versions(c)
    assert history[0].paragraphs == [""]
    assert history[1].paragraphs == ["A replacement.", "New final paragraph."]
    assert history[2].paragraphs == original
    restored = restore(c, history[2].id, revision=empty.revision)
    assert [p.current for p in restored.paragraphs] == original
    assert restored.revision == empty.revision + 1
    history = versions(c)
    assert len(history) == 4
    assert history[0].change_type == "restored"
    assert history[0].restored_from_id == history[-1].id
    assert [v.revision for v in history] == [4, 3, 2, 1]
    # Empty scripts themselves remain restorable, too.
    empty_version = next(v for v in history if v.paragraphs == [""])
    current = c.session.get(SlideTranscript, restored.transcript_id)
    again = restore(c, empty_version.id, transcript=current)
    assert [p.current for p in again.paragraphs] == [""]
    assert len(versions(c)) == 5


def test_generation_regeneration_and_enhancement_share_history(setup):
    c = setup
    first = api._save_ai_slide_transcript(
        c.session,
        c.presentation,
        c.slide,
        {"paragraphs": ["First script.", "Keep this."], "complex_terms": []},
        75,
        "conversational",
        "natural",
        "beginner",
    )
    c.session.commit()
    second = api._save_ai_slide_transcript(
        c.session,
        c.presentation,
        c.slide,
        {"paragraphs": ["Regenerated script."]},
        105,
        "informative",
        "formal",
        "specialist",
    )
    c.session.commit()
    history = versions(c)
    assert [v.change_type for v in history] == ["generated", "generated", "saved"]
    assert history[1].paragraphs == ["First script.", "Keep this."]
    assert history[1].settings["audience_level"] == "beginner"
    assert history[0].settings["duration_seconds"] == 105
    result = restore(c, history[1].id, transcript=second)
    assert [p.current for p in result.paragraphs] == ["First script.", "Keep this."]
    assert result.requested_tone == "conversational"
    assert result.requested_audience_level == "beginner"
    assert result.requested_duration_seconds == 75
    assert first.id != result.transcript_id
    assert history[1].id in [v.id for v in versions(c)]


def test_legacy_saved_script_visible_without_writes_and_restorable(setup):
    c = setup
    legacy = versions(c)
    assert len(legacy) == 1 and legacy[0].legacy
    assert list(c.session.scalars(select(TranscriptVersion))) == []
    accept(c)
    result = restore(c, legacy[0].id)
    assert [p.current for p in result.paragraphs] == legacy[0].paragraphs


def test_restore_never_calls_provider_and_preserves_matching_feedback(setup, monkeypatch):
    c = setup
    c.transcript.tone_classification = "Informative"
    c.transcript.tone_rationale = "Original explanation."
    c.session.add(
        TranscriptComplexTerm(
            slide_transcript_id=c.transcript.id,
            term="SME",
            definition="Small business",
            pronunciation_text="ess em ee",
        )
    )
    c.session.commit()
    accept(c)
    original = versions(c)[-1]

    def no_provider(*_a, **_k):
        pytest.fail("Restoring saved text must not request AI generation or analysis")

    monkeypatch.setattr(api, "analyze_script", no_provider)
    monkeypatch.setattr(api, "generate_script", no_provider)
    result = restore(c, original.id)
    assert result.tone_check.rationale == "Original explanation."
    assert result.complex_terms[0].term == "SME"
    assert result.vocabulary_upgrades == []


def test_stale_restore_rejected_without_history_or_text_changes(setup):
    c = setup
    accept(c)
    history = versions(c)
    texts = [p.current_text for p in api._paragraphs(c.session, c.transcript.id)]
    with pytest.raises(HTTPException) as error:
        restore(c, history[-1].id, revision=1)
    assert error.value.status_code == 409
    assert len(versions(c)) == len(history)
    assert [p.current_text for p in api._paragraphs(c.session, c.transcript.id)] == texts


def test_history_and_restore_enforce_owner_and_slide_boundaries(setup):
    c = setup
    accept(c)
    version_id = versions(c)[-1].id
    stranger = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        api.transcript_versions(c.presentation.id, 1, c.session, stranger)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        api.restore_transcript_version(
            c.presentation.id,
            1,
            version_id,
            api.RestoreVersionRequest(slide_transcript_id=c.transcript.id, base_revision=2),
            c.session,
            stranger,
        )
    assert error.value.status_code == 404
    other = Slide(presentation_id=c.presentation.id, slide_number=2, extracted_content={})
    c.session.add(other)
    c.session.flush()
    other_script = api._create_human_draft(c.session, c.presentation, other)
    c.session.commit()
    with pytest.raises(HTTPException) as error:
        api.restore_transcript_version(
            c.presentation.id,
            2,
            version_id,
            api.RestoreVersionRequest(slide_transcript_id=other_script.id, base_revision=1),
            c.session,
            c.user,
        )
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        restore(c, uuid.uuid4())
    assert error.value.status_code == 404


def test_current_version_restore_rejected(setup):
    c = setup
    accept(c)
    with pytest.raises(HTTPException) as error:
        restore(c, versions(c)[0].id)
    assert error.value.status_code == 409
    assert len(versions(c)) == 2


def test_old_transcript_cannot_overwrite_new_generation_with_restore(setup):
    c = setup
    accept(c)
    version_id = versions(c)[-1].id
    generated = api._save_ai_slide_transcript(
        c.session,
        c.presentation,
        c.slide,
        {"paragraphs": ["Newest."]},
        75,
        "auto",
        "natural",
        "general",
    )
    c.session.commit()
    with pytest.raises(HTTPException) as error:
        restore(c, version_id)
    assert error.value.status_code == 409
    latest, _ = api._latest_by_slide(c.session, c.presentation.id)
    assert latest[c.slide.id].id == generated.id


def test_version_routes_serialize_and_restore_through_http(setup):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    c = setup
    accept(c)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db_session] = lambda: c.session
    app.dependency_overrides[api.authenticated_user] = lambda: c.user
    base = f"/api/v1/presentations/{c.presentation.id}/transcript/slides/1/versions"
    with TestClient(app) as client:
        response = client.get(base)
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 2
        assert len(entries[-1]["paragraphs"]) == 3
        response = client.post(
            f"{base}/{entries[-1]['id']}/restore",
            json={
                "slide_transcript_id": str(c.transcript.id),
                "base_revision": 2,
            },
        )
        assert response.status_code == 200
        assert response.json()["paragraphs"][-1]["current"] == "Unselected paragraph."
        assert client.get(base).json()[0]["change_type"] == "restored"


def test_bulk_replace_existing_generates_written_slides_and_preserves_history(setup, monkeypatch):
    c = setup
    original = [p.current_text for p in c.parts]
    presentation_id, slide_id, user_id = c.presentation.id, c.slide.id, c.user.id
    _prepare_bulk_case(c, [2, 3])
    c.slide.extracted_content = {"num": 1, "text": "First slide"}
    c.session.commit()
    calls = []

    def generate(slide, **kwargs):
        calls.append(slide["num"])
        return {"paragraphs": [f"New script {slide['num']}."]}

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(
        c.presentation.id, 75, "informative", "natural", 1, 2, replace_existing=True
    )
    assert sorted(calls) == [1, 2]
    c.presentation = c.session.get(Presentation, presentation_id)
    c.slide = c.session.get(Slide, slide_id)
    c.user = c.session.get(User, user_id)
    history = versions(c)
    assert history[0].paragraphs == ["New script 1."]
    assert history[1].paragraphs == original
    assert history[0].change_type == "generated"
    latest, _ = api._latest_by_slide(c.session, c.presentation.id)
    third = c.session.scalar(
        select(Slide).where(Slide.presentation_id == c.presentation.id, Slide.slide_number == 3)
    )
    assert third.id not in latest


def test_bulk_replace_existing_preserves_newer_manual_edit(setup, monkeypatch):
    c = setup
    job_id = _prepare_bulk_case(c, [])
    presentation_id, slide_id, transcript_id = c.presentation.id, c.slide.id, c.transcript.id
    ready = Event()
    changed = False
    latest = api._latest_by_slide

    def generate(*_args, **_kwargs):
        ready.set()
        return {"paragraphs": ["Late replacement must not win."]}

    def saved_while_running(session, presentation_id):
        nonlocal changed
        if ready.is_set() and not changed:
            changed = True
            c.parts[0].current_text = "A newer human edit."
            c.transcript.revision += 1
            session.flush()
        return latest(session, presentation_id)

    monkeypatch.setattr(api, "generate_script", generate)
    monkeypatch.setattr(api, "_latest_by_slide", saved_while_running)
    monkeypatch.setattr(api, "get_session_factory", lambda: lambda: c.session)
    api.run_generate_all_transcripts(
        c.presentation.id, 75, "informative", "natural", 1, 1, replace_existing=True
    )
    assert c.session.get(Job, job_id).status == "completed"
    assert c.parts[0].current_text == "A newer human edit."
    assert latest(c.session, presentation_id)[0][slide_id].id == transcript_id


def test_bulk_replace_existing_is_opt_in_and_forwarded_to_worker(setup):
    from fastapi import BackgroundTasks

    c = setup
    assert api.GenerateAllRequest(start_slide=1, end_slide=1).replace_existing is False
    tasks = BackgroundTasks()
    api.generate_all_slide_transcripts(
        c.presentation.id,
        api.GenerateAllRequest(start_slide=1, end_slide=1, replace_existing=True),
        tasks,
        c.session,
        c.user,
    )
    assert tasks.tasks[0].args[-1] is True
