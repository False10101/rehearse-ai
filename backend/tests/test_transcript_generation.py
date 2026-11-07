import json

import pytest

from app.services import transcript_enhancer


def _generation_response(paragraphs, tone="Informative"):
    return {
        "paragraphs": paragraphs,
        "tone_check": {
            "classification": tone,
            "confidence": 0.9,
            "rationale": "Delivery feedback.",
        },
        "complex_terms": [],
        "vocabulary_upgrades": [],
    }


@pytest.mark.parametrize("duration", [45, 75, 105])
@pytest.mark.parametrize("tone", ["auto", "informative", "persuasive", "conversational"])
@pytest.mark.parametrize("style", ["natural", "formal"])
@pytest.mark.parametrize("audience", ["beginner", "general", "specialist"])
def test_all_generation_settings_use_one_response_for_speech_and_feedback(
    monkeypatch, duration, tone, style, audience
):
    calls = []
    response = _generation_response(["The actual words I will say to the audience."])

    def request(prompt, **kwargs):
        calls.append(prompt)
        return response

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    result = transcript_enhancer.generate_script({}, duration, tone, style, audience_level=audience)
    assert len(calls) == 1
    assert result == response
    assert "exact words the presenter will say aloud" in calls[0]
    assert f"Length baseline: {duration} seconds" in calls[0]
    assert transcript_enhancer.TONE_RULES[tone] in calls[0]
    assert transcript_enhancer.STYLE_RULES[style] in calls[0]
    assert transcript_enhancer.AUDIENCE_RULES[audience] in calls[0]


@pytest.mark.parametrize("tone", ["auto", "informative", "persuasive", "conversational"])
@pytest.mark.parametrize("style", ["natural", "formal"])
@pytest.mark.parametrize("audience", ["beginner", "general", "specialist"])
def test_enhancement_settings_reach_one_selected_text_request(monkeypatch, tone, style, audience):
    calls = []

    def request(prompt, **kwargs):
        calls.append(prompt)
        return {"replacement_paragraphs": ["the revised fragment"]}

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    assert transcript_enhancer.enhance_selection(
        {}, ["the old fragment"], tone, style, audience
    ) == ["the revised fragment"]
    assert len(calls) == 1
    assert transcript_enhancer.TONE_RULES[tone] in calls[0]
    assert transcript_enhancer.STYLE_RULES[style] in calls[0]
    assert transcript_enhancer.AUDIENCE_RULES[audience] in calls[0]


@pytest.mark.parametrize("raw", [[], ["  "], "not a list"])
def test_invalid_generated_text_fails_without_another_ai_call(monkeypatch, raw):
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return {"paragraphs": raw}

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    with pytest.raises(ValueError):
        transcript_enhancer.generate_script({}, 75, "informative", "natural")
    assert len(calls) == 1


@pytest.mark.parametrize("feedback", [{}, {"tone_check": "malformed"}])
def test_unusable_feedback_keeps_spoken_text_without_second_call(monkeypatch, feedback):
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return {"paragraphs": ["Thank you for listening."], **feedback}

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    result = transcript_enhancer.generate_script({}, 105, "conversational", "formal")
    assert result == {"paragraphs": ["Thank you for listening."]}
    assert len(calls) == 1


def test_provider_error_is_not_a_content_retry(monkeypatch):
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("Provider unavailable")

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    with pytest.raises(RuntimeError, match="Provider unavailable"):
        transcript_enhancer.generate_script({}, 75, "informative", "natural")
    assert len(calls) == 1


def test_feedback_disagreement_and_extra_editor_fields_do_not_rewrite_speech(monkeypatch):
    response = _generation_response(["Let's look at this finding together."], "Informative")
    response.update(
        page_role="opening",
        opening_introduction="Do not append this.",
        edit_notes=["Private"],
        grounding_issues=["Do not speak this."],
        reviewed_paragraphs=["Do not replace the script."],
    )
    calls = []

    def request(*args, **kwargs):
        calls.append(args)
        return response

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    result = transcript_enhancer.generate_script({}, 75, "conversational", "formal")
    assert result == {
        key: response[key]
        for key in ["paragraphs", "tone_check", "complex_terms", "vocabulary_upgrades"]
    }
    assert len(calls) == 1


def test_repetitive_or_short_prose_is_not_rejected_by_a_backend_quality_gate(monkeypatch):
    speech = ["The result matters. The result matters."]
    monkeypatch.setattr(
        transcript_enhancer, "_request_json", lambda *a, **k: _generation_response(speech)
    )
    assert (
        transcript_enhancer.generate_script({}, 105, "informative", "formal")["paragraphs"]
        == speech
    )
    assert transcript_enhancer._spoken_paragraphs({"paragraphs": ["First.\n\nSecond."]}) == [
        "First.",
        "Second.",
    ]


def test_source_and_continuity_do_not_import_future_slide_content(monkeypatch):
    calls = []

    def request(prompt, **kwargs):
        calls.append(prompt)
        return _generation_response(["Current subject."])

    monkeypatch.setattr(transcript_enhancer, "_request_json", request)
    current = {"num": 1, "text": [{"t": "Current source fact"}]}
    future = {"num": 2, "title": "Later subject", "text": [{"t": "Future body fact"}]}
    transcript_enhancer.generate_script(
        current,
        75,
        "informative",
        "formal",
        next_slide=future,
        deck_slides=[current, future],
        neighboring_scripts=[{"slide_number": 2, "script": "Future saved script"}],
    )
    assert "Current source fact" in calls[0]
    assert "Later subject" in calls[0]
    assert "Future body fact" not in calls[0]
    assert "Future saved script" not in calls[0]


def test_feedback_has_no_content_blacklist_acronym_placeholders_or_caps(monkeypatch):
    terms = ["SME", "upskilling hub", "Bayesian inference"] + [f"metric {i}" for i in range(8)]
    speech = ["; ".join(terms)]
    response = _generation_response(speech)
    response["complex_terms"] = [
        {"term": t, "definition": f"Meaning of {t}", "pronunciation": "réh-zuhlts"} for t in terms
    ]
    response["vocabulary_upgrades"] = [
        {"original": t, "suggested": f"clearer {t}", "reason": "Slight wording improvement."}
        for t in terms[:4]
    ]
    monkeypatch.setattr(transcript_enhancer, "_request_json", lambda *a, **k: response)
    result = transcript_enhancer.analyze_script(speech)
    assert [t["term"] for t in result["complex_terms"]] == terms
    assert len(result["vocabulary_upgrades"]) == 4
    response["complex_terms"] = []
    assert transcript_enhancer.analyze_script(speech)["complex_terms"] == []


def test_feedback_only_filters_quotes_that_are_absent_not_words_it_dislikes(monkeypatch):
    speech = ["The SME prepares an initial finding."]
    response = _generation_response(speech)
    response["complex_terms"] = [
        {
            "term": "SME",
            "definition": "A small or medium-sized enterprise.",
            "pronunciation": "ess em ee",
        },
        {
            "term": "ME",
            "definition": "Not a standalone word in this script.",
            "pronunciation": "em ee",
        },
    ]
    response["vocabulary_upgrades"] = [
        {"original": "initial finding", "suggested": "early finding", "reason": "Slight change."},
        {"original": "initial finding", "suggested": "", "reason": "Unusable empty replacement."},
        {"original": "unspoken words", "suggested": "other words", "reason": "Not in the script."},
    ]
    monkeypatch.setattr(transcript_enhancer, "_request_json", lambda *a, **k: response)
    result = transcript_enhancer.analyze_script(speech)
    assert [t["term"] for t in result["complex_terms"]] == ["SME"]
    assert len(result["vocabulary_upgrades"]) == 1
    assert result["vocabulary_upgrades"][0]["suggested"] == "early finding"


def test_source_preserves_tables_charts_and_full_text():
    chart = {"categories": ["A"], "values": [4]}
    source = json.loads(
        transcript_enhancer._writing_source(
            {
                "num": 2,
                "text": "A complete source string",
                "charts": [chart],
                "tables": [{"rows": [["A", "4"]]}],
                "img_context": "Observer notes",
            }
        )
    )
    assert source["text_content"] == ["A complete source string"]
    assert source["charts"] == [chart]
    assert source["tables"] == [{"rows": [["A", "4"]]}]
    assert source["visual_reference"] == "Observer notes"


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


def test_human_script_analysis_never_applies_model_rewrite(monkeypatch):
    original = ["The user's exact words."]
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {
            "reviewed_paragraphs": ["Unrequested rewrite"],
            "complex_terms": [],
            "tone_check": {
                "classification": "Informative",
                "confidence": 0.9,
                "rationale": "A neutral explanation.",
            },
            "vocabulary_upgrades": [],
            "grounding_issues": [],
        },
    )
    result = transcript_enhancer.analyze_script(original)
    assert "paragraphs" not in result
    assert original == ["The user's exact words."]


def test_analysis_remains_feedback_only_even_with_generation_settings(monkeypatch):
    response = _generation_response(["Unrequested rewrite"])
    response["reviewed_paragraphs"] = ["Another unrequested rewrite"]
    monkeypatch.setattr(transcript_enhancer, "_request_json", lambda *a, **k: response)
    original = ["The user's exact words."]
    result = transcript_enhancer.analyze_script(
        original,
        {
            "generation_settings": {
                "tone": "informative",
                "style": "formal",
                "audience_level": "general",
                "duration_seconds": 75,
            }
        },
    )
    assert "paragraphs" not in result
    assert original == ["The user's exact words."]


def test_analysis_filters_terms_against_supplied_speech_without_rewriting(monkeypatch):
    response = _generation_response(["Unused model speech."])
    response["complex_terms"] = [
        {
            "term": "unspoken term",
            "definition": "A definition.",
            "pronunciation": "un spoken term",
            "why_complex": "Specialized.",
        }
    ]
    monkeypatch.setattr(transcript_enhancer, "_request_json", lambda *a, **k: response)
    result = transcript_enhancer.analyze_script(["The actual user script."])
    assert result["complex_terms"] == []


@pytest.mark.parametrize(
    "original,replacement,after,expected",
    [
        (" the old phrase ", "the revised phrase", "continues", " the revised phrase "),
        ("the old phrase", "the revised phrase.", ". Next sentence.", "the revised phrase"),
        ("the old phrase", "the revised phrase,", ", with context", "the revised phrase"),
        ("the old phrase.", "the revised phrase.", "..", "the revised phrase."),
    ],
)
def test_enhancement_preserves_fragment_spacing_and_existing_punctuation(
    monkeypatch, original, replacement, after, expected
):
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {
            "replacement_paragraphs": [replacement],
        },
    )
    result = transcript_enhancer.enhance_selection(
        {}, [original], "informative", "formal", surrounding_text={"after": after}
    )
    assert result == [expected]


def test_continuity_context_contains_titles_and_only_previous_script_endings():
    before = {"num": 1, "title": "Introduction", "text": [{"t": "Old material"}]}
    current = {"num": 2, "title": "Results"}
    after = {"num": 3, "title": "Next steps", "text": [{"t": "Future material"}]}
    context = transcript_enhancer._continuity_context(
        current,
        before,
        after,
        [before, current, after],
        [{"slide_number": 1, "script": "x" * 1000}, {"slide_number": 3, "script": "Future script"}],
    )
    assert context["slide_sequence"] == [
        {"slide_number": 1, "title": "Introduction"},
        {"slide_number": 2, "title": "Results"},
        {"slide_number": 3, "title": "Next steps"},
    ]
    assert context["previous_script_endings"] == [{"slide_number": 1, "ending": "x" * 700}]
    assert "Old material" not in str(context)
    assert "Future material" not in str(context)


@pytest.mark.parametrize(
    "boundary,replacement,expected",
    [
        (True, "The result is supported", "The result is supported."),
        (False, "The result is supported", "The result is supported"),
        (True, "Is the result supported?", "Is the result supported?"),
    ],
)
def test_enhancement_restores_existing_end_mark_only_at_paragraph_boundary(
    monkeypatch, boundary, replacement, expected
):
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {"replacement_paragraphs": [replacement]},
    )
    result = transcript_enhancer.enhance_selection(
        {},
        ["The result is supported."],
        "informative",
        "formal",
        selection_boundaries={"last_part_ends_paragraph": boundary},
    )
    assert result == [expected]


def test_enhancement_restores_internal_paragraph_end_without_touching_final_fragment(monkeypatch):
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {"replacement_paragraphs": ["the wait was lower", "Other factors matter"]},
    )
    result = transcript_enhancer.enhance_selection(
        {},
        ["the wait was lower.", "Other factors matter"],
        "informative",
        "formal",
        surrounding_text={"before": "We observed that ", "after": ". We will test again."},
        selection_boundaries={
            "first_part_starts_paragraph": False,
            "last_part_ends_paragraph": False,
        },
    )
    assert result == ["the wait was lower.", "Other factors matter"]


@pytest.mark.parametrize(
    "boundary,replacement,expected",
    [
        (
            True,
            "because the comparison was observational",
            "Because the comparison was observational",
        ),
        (
            False,
            "because the comparison was observational",
            "because the comparison was observational",
        ),
        (True, "iPhone supports this feature", "iPhone supports this feature"),
        (True, "mRNA carries the instructions", "mRNA carries the instructions"),
        (True, "“because the groups differed”", "“Because the groups differed”"),
    ],
)
def test_selection_sentence_case_respects_boundaries_and_mixed_case_names(
    monkeypatch, boundary, replacement, expected
):
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {"replacement_paragraphs": [replacement]},
    )
    result = transcript_enhancer.enhance_selection(
        {},
        [replacement],
        "informative",
        "formal",
        selection_boundaries={"first_part_starts_paragraph": boundary},
    )
    assert result == [expected]


def test_selection_starts_later_paragraphs_as_sentences(monkeypatch):
    monkeypatch.setattr(
        transcript_enhancer,
        "_request_json",
        lambda *a, **k: {
            "replacement_paragraphs": ["the waits differed.", "because the groups differed"]
        },
    )
    assert transcript_enhancer.enhance_selection(
        {},
        ["the waits differed.", "because the groups differed"],
        "informative",
        "formal",
        selection_boundaries={"first_part_starts_paragraph": False},
    ) == ["the waits differed.", "Because the groups differed"]


def test_writer_prefers_complete_paragraphs_to_fragmented_formatting_runs():
    import json

    source = json.loads(
        transcript_enhancer._writing_source(
            {
                "num": 3,
                "text": [{"t": "Sam"}, {"t": "ira"}, {"t": "H."}],
                "paragraphs": [{"text": "Samira H."}, {"text": "  "}],
            }
        )
    )
    assert source["text_content"] == ["Samira H."]


def test_cut_off_json_logs_finish_reason_and_token_usage(caplog):
    import json

    import requests

    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {"content": '{"paragraphs":["unfinished'},
                }
            ],
            "usage": {"completion_tokens": 6000},
        }
    ).encode()
    with pytest.raises(json.JSONDecodeError):
        transcript_enhancer._parse_json_content(response)
    assert "finish_reason='length'" in caplog.text
    assert "completion_tokens" in caplog.text
    assert "unfinished" in caplog.text
