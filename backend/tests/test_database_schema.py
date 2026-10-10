import app.db.models  # noqa: F401
from app.db.base import Base


def test_initial_schema_contains_core_product_tables() -> None:
    expected_tables = {
        "users",
        "presentations",
        "slides",
        "presentation_analyses",
        "slide_analyses",
        "analysis_complex_terms",
        "presentation_transcripts",
        "slide_transcripts",
        "transcript_paragraphs",
        "transcript_complex_terms",
        "slide_vocabulary_upgrades",
        "transcript_revisions",
        "upload_practice_sessions",
        "jobs",
    }

    assert expected_tables <= set(Base.metadata.tables)
    assert "uq_slides_presentation_number" in {
        constraint.name for constraint in Base.metadata.tables["slides"].constraints
    }


def test_user_model_uses_auth0_identity_without_local_passwords() -> None:
    user_columns = set(Base.metadata.tables["users"].columns.keys())

    assert "auth0_subject" in user_columns
    assert "password_hash" not in user_columns
    assert "google_subject" not in user_columns


def test_presentation_analysis_keeps_the_full_model_output() -> None:
    analysis_columns = set(Base.metadata.tables["presentation_analyses"].columns.keys())

    assert "raw_output" in analysis_columns


def test_live_practice_does_not_define_persistent_storage() -> None:
    assert "live_practice_sessions" not in Base.metadata.tables


def test_upload_practice_stores_delivery_metrics() -> None:
    columns = set(Base.metadata.tables["upload_practice_sessions"].columns.keys())

    assert {
        "filler_clusters",
        "pause_events",
        "pace_samples",
        "timed_transcript",
        "speech_moments",
        "pace_events",
        "repetition_events",
    } <= columns
