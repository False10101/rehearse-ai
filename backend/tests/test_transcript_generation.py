import pytest

from app.services import transcript_enhancer
from app.services.transcript_enhancer import _validate_spoken_script


def test_rejects_analytical_slide_commentary() -> None:
    analytical_sentence = (
        "What stands out here is how the participant keeps moving between tools "
        "while the observation gives us evidence of a broader pattern."
    )
    analytical_paragraph = " ".join([analytical_sentence] * 4)

    with pytest.raises(ValueError, match="slide analysis"):
        _validate_spoken_script(
            {"paragraphs": [analytical_paragraph, analytical_paragraph]},
            duration_seconds=75,
        )


def test_accepts_a_speaker_ready_standard_length_script() -> None:
    opening_sentence = (
        "To understand this point, I want to focus on the work that happens "
        "before a solution becomes visible."
    )
    explanation_sentence = (
        "The key idea is that progress comes from testing, revising, and learning "
        "from each attempt, so this process matters as much as the final result."
    )
    opening = " ".join([opening_sentence] * 4)
    explanation = " ".join([explanation_sentence] * 4)

    assert _validate_spoken_script(
        {"paragraphs": [opening, explanation]},
        duration_seconds=75,
    ) == [opening, explanation]


def test_coaching_filters_marginal_terms_and_unsafe_rewrites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paragraphs = [
        "Our AI matching feature uses Bayesian inference to compare each SME "
        "with the available signals. "
        "The last piece is a very long phrase that we can explain more directly."
    ]
    model_response = {
        "complex_terms": [
            {
                "term": "AI matching",
                "definition": "Matching performed with artificial intelligence.",
                "pronunciation": "ay eye matching",
                "why_complex": "It is a technology phrase.",
            },
            {
                "term": "Bayesian inference",
                "definition": "A method that updates estimates when new evidence appears.",
                "pronunciation": "bay zee un inference",
                "why_complex": "The script does not explain this specialized statistical method.",
            },
        ],
        "tone_check": {
            "classification": "Informative",
            "confidence": 0.9,
            "rationale": "The script explains the process in neutral language.",
        },
        "vocabulary_upgrades": [
            {
                "original": "compare the available signals",
                "suggested": "accurately compare the available signals",
                "reason": "Makes the benefit clearer.",
                "issue": "unclear",
            },
            {
                "original": "a very long phrase",
                "suggested": "a concise phrase",
                "reason": "Removes unnecessary words.",
                "issue": "wordy",
            },
        ],
        "grounding_issues": [],
    }
    monkeypatch.setattr(
        transcript_enhancer, "_request_json", lambda *_args, **_kwargs: model_response
    )

    analysis = transcript_enhancer.analyze_script(paragraphs)

    assert [term["term"] for term in analysis["complex_terms"]] == [
        "Bayesian inference",
        "SME",
    ]
    assert analysis["complex_terms"][1]["pronunciation"] == "ess em ee"
    assert analysis["vocabulary_upgrades"] == [
        {
            "original": "a very long phrase",
            "suggested": "a concise phrase",
            "reason": "Removes unnecessary words.",
        }
    ]


def test_generation_retries_an_unsupported_first_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentence = (
        "This feature uses the listed profile details to compare a candidate with a role, "
        "and the result gives the audience a clear view of the stated matching process."
    )
    draft = {"paragraphs": [" ".join([sentence] * 3), " ".join([sentence] * 3)]}
    responses = iter(
        [
            draft,
            {
                "complex_terms": [],
                "tone_check": {
                    "classification": "Informative",
                    "confidence": 0.9,
                    "rationale": "The script explains the process neutrally.",
                },
                "vocabulary_upgrades": [],
                "grounding_issues": ["The script claims the result is clear to the audience."],
            },
            draft,
            {
                "complex_terms": [],
                "tone_check": {
                    "classification": "Informative",
                    "confidence": 0.9,
                    "rationale": "The script explains the process neutrally.",
                },
                "vocabulary_upgrades": [],
                "grounding_issues": [],
            },
        ]
    )
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )
    slide = {"num": 3, "title": "Matching", "text": [{"t": "Compare profile details"}]}

    result = transcript_enhancer.generate_script(
        slide=slide,
        duration_seconds=75,
        tone="informative",
        style="natural",
        deck_slides=[slide],
    )

    assert result["paragraphs"] == draft["paragraphs"]
    assert result["grounding_issues"] == []


def test_coaching_tolerates_and_sanitizes_extra_grounding_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = {
        "complex_terms": [],
        "tone_check": {
            "classification": "Informative",
            "confidence": 0.8,
            "rationale": "The script explains the subject neutrally.",
        },
        "vocabulary_upgrades": [],
        "grounding_issues": [
            "Unsupported claim one.",
            "Unsupported claim two.",
            "This statement is supported by the source.",
            "Unsupported claim three.",
            "Unsupported claim four.",
            "Unsupported claim five.",
        ],
    }
    monkeypatch.setattr(transcript_enhancer, "_request_json", lambda *_args, **_kwargs: response)

    result = transcript_enhancer.analyze_script(["A short ordinary script."])

    assert result["grounding_issues"] == [
        "Unsupported claim one.",
        "Unsupported claim two.",
        "Unsupported claim three.",
        "Unsupported claim four.",
    ]


def test_generation_uses_a_valid_fallback_after_grounding_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentence = (
        "This feature uses the listed profile details to compare a candidate with a role, "
        "and the result presents the stated matching process in direct spoken language."
    )
    draft = {"paragraphs": [" ".join([sentence] * 3), " ".join([sentence] * 3)]}
    analysis = {
        "complex_terms": [],
        "tone_check": {
            "classification": "Informative",
            "confidence": 0.9,
            "rationale": "The script explains the process neutrally.",
        },
        "vocabulary_upgrades": [],
        "grounding_issues": ["The reviewer considered one phrase interpretive."],
    }
    responses = iter([draft, analysis, draft, analysis, draft, analysis])
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *_args, **_kwargs: next(responses),
    )
    slide = {"num": 3, "title": "Matching", "text": [{"t": "Compare profile details"}]}

    result = transcript_enhancer.generate_script(
        slide=slide,
        duration_seconds=75,
        tone="informative",
        style="natural",
        deck_slides=[slide],
    )

    assert result["paragraphs"] == draft["paragraphs"]


def test_enhancement_preserves_selected_paragraph_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *_args, **_kwargs: {
            "replacement_paragraphs": ["Improved first passage.", "Improved second passage."]
        },
    )

    result = transcript_enhancer.enhance_selection(
        slide={"num": 8, "title": "Closing", "text": []},
        selected_parts=["First passage.", "Second passage."],
        tone="conversational",
        style="formal",
    )

    assert result == ["Improved first passage.", "Improved second passage."]


def test_enhancement_rejects_a_merged_multi_paragraph_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *_args, **_kwargs: {
            "replacement_paragraphs": ["The model incorrectly merged both passages."]
        },
    )

    with pytest.raises(ValueError, match="preserve the selected paragraph structure"):
        transcript_enhancer.enhance_selection(
            slide={"num": 8, "title": "Closing", "text": []},
            selected_parts=["First passage.", "Second passage."],
            tone="conversational",
            style="formal",
        )
