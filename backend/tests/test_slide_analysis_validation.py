import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services import slide_analyzer


def test_provider_error_logs_full_body_without_key(monkeypatch, caplog) -> None:
    response = slide_analyzer.requests.Response()
    response.status_code = 404
    detail = "No endpoints found supporting all requested parameters. " + "x" * 1200
    response._content = json.dumps({"error": {"message": detail, "key": "test-secret"}}).encode()

    def fake_post(*_args, **_kwargs):
        response.raise_for_status()

    monkeypatch.setattr(slide_analyzer.requests, "post", fake_post)
    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(
        slide_analyzer, "get_settings", lambda: SimpleNamespace(openrouter_api_key="test-secret")
    )
    with pytest.raises(slide_analyzer.SlideAnalysisGenerationError) as caught:
        slide_analyzer.analyze([{"num": 1, "text": []}])

    assert detail in caplog.text
    assert "HTTP 404" in caplog.text
    assert "[REDACTED]" in caplog.text
    assert "test-secret" not in caplog.text
    assert detail not in caught.value.diagnostic
    assert caplog.text.count("OpenRouter error response") == 1
    assert "before retrying" in str(caught.value)


def valid_analysis() -> dict:
    return {
        "overall_score": 7.5,
        "score_rationale": "The deck is coherent. Its evidence can be clearer.",
        "deck_top_priorities": ["[LOW] Slide 1: distinguish the subtitle from the body text."],
        "examiner_red_flags": [],
        "agenda_status": "missing",
        "cohesion_feedback": "The sequence is logical. Strengthen the final transition.",
        "per_slide": [
            {
                "num": 1,
                "slide_score": 7.5,
                "overload": False,
                "overload_reason": None,
                "visual_hierarchy_issues": None,
                "improvement_suggestions": ["[LOW] Strengthen the subtitle."],
                "table_tips": [],
                "refs_found": [],
            }
        ],
        "complex_terms": [],
    }


def test_saved_visual_reviews_remain_valid_and_legacy_results_load():
    old = valid_analysis()
    parsed_old = slide_analyzer.validate_slide_analysis_result(old, [1])
    assert parsed_old["per_slide"][0]["visual_reviews"] == []
    updated = valid_analysis()
    updated["per_slide"][0]["visual_reviews"] = [{
        "check_id": "readability-1", "status": "uncertain",
        "reason": "Small caption; visibility uncertain.",
        "suggestion": None,
    }]
    parsed = slide_analyzer.validate_slide_analysis_result(updated, [1])
    assert slide_analyzer.validate_slide_analysis_result(parsed, [1]) == parsed


class FakeResponse:
    def __init__(self, content: dict):
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": json.dumps(self.content)}}]}


def test_validation_rejects_missing_complex_terms() -> None:
    result = valid_analysis()
    result.pop("complex_terms")

    with pytest.raises(ValidationError):
        slide_analyzer.validate_slide_analysis_result(result, [1])


def test_validation_rejects_missing_slide_result() -> None:
    with pytest.raises(ValueError, match="exactly one result"):
        slide_analyzer.validate_slide_analysis_result(valid_analysis(), [1, 2])


def test_analyze_retries_invalid_payload_then_returns_valid_payload(monkeypatch) -> None:
    invalid = valid_analysis()
    invalid.pop("complex_terms")
    responses = iter([FakeResponse(invalid), FakeResponse(invalid), FakeResponse(valid_analysis())])
    attempts = 0

    def fake_post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return next(responses)

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", fake_post)

    result = slide_analyzer.analyze([{"num": 1}])

    assert attempts == 3
    assert result["complex_terms"] == []


def test_analyze_fails_after_three_invalid_payloads(monkeypatch) -> None:
    invalid = valid_analysis()
    invalid.pop("complex_terms")
    attempts = 0

    def fake_post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse(invalid)

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", fake_post)

    with pytest.raises(slide_analyzer.SlideAnalysisGenerationError):
        slide_analyzer.analyze([{"num": 1}])

    assert attempts == 3


def test_zero_priorities_are_valid_without_fabricating_padding() -> None:
    result = valid_analysis()
    result["deck_top_priorities"] = []
    parsed = slide_analyzer.validate_slide_analysis_result(result, [1])
    slide_analyzer.validate_generated_findings(parsed, [{"num": 1}])
    assert parsed["deck_top_priorities"] == []


@pytest.mark.parametrize(
    "suggestions,error",
    [
        (["[LOW] Refine the wording."] * 4, "duplicate|repeat|distinct"),
    ],
)
def test_every_slide_requires_concise_non_redundant_coaching(suggestions, error) -> None:
    result = valid_analysis()
    result["per_slide"][0]["improvement_suggestions"] = suggestions

    with pytest.raises(ValueError, match=error):
        slide_analyzer.validate_generated_findings(result, [{"num": 1}])


def test_more_than_three_deck_priorities_still_rejected() -> None:
    result = valid_analysis()
    result["deck_top_priorities"] *= 4
    with pytest.raises(ValidationError):
        slide_analyzer.validate_slide_analysis_result(result, [1])


def test_per_slide_suggestions_have_no_fixed_maximum() -> None:
    result = valid_analysis()
    suggestions = [f"[MEDIUM] Correct distinct source issue {index}." for index in range(12)]
    result["per_slide"][0]["improvement_suggestions"] = suggestions
    parsed = slide_analyzer.validate_slide_analysis_result(result, [1])
    slide_analyzer.validate_generated_findings(parsed, [{"num": 1}])
    assert parsed["per_slide"][0]["improvement_suggestions"] == suggestions
    schema = slide_analyzer.analysis_response_format([1])["json_schema"]["schema"]
    # The strict provider schema must not reintroduce the old three-item limit.
    assert (
        "maxItems"
        not in schema["$defs"]["SlideAnalysisPayload"]["properties"]["improvement_suggestions"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("improvement_suggestions", ["N/A"]),
        ("improvement_suggestions", ["[LOW] Improve the title.", "[HIGH] Improve the title."]),
        ("table_tips", [""]),
    ],
)
def test_new_findings_reject_invented_references_and_unusable_lists(field, value) -> None:
    result = valid_analysis()
    result["per_slide"][0][field] = value
    with pytest.raises(ValueError):
        slide_analyzer.validate_generated_findings(result, [{"num": 1}])


def test_reference_not_found_on_its_slide_is_filtered() -> None:
    result = valid_analysis()
    result["per_slide"][0]["refs_found"] = ["Smith (2024)"]
    slide_analyzer.validate_generated_findings(
        result,
        [
            {"num": 1},
            {"num": 2, "text": [{"t": "Smith (2024)"}]},
        ],
    )
    assert result["per_slide"][0]["refs_found"] == []


def test_source_references_support_split_runs_and_table_cells() -> None:
    result = valid_analysis()
    result["per_slide"][0]["refs_found"] = ["https://example.org/paper", "Smith (2024)"]
    slide_analyzer.validate_generated_findings(
        result,
        [
            {
                "num": 1,
                "text": [{"t": "https://example."}, {"t": "org/paper"}],
                "tables": [[["Source", "Smith (2024)"]]],
            }
        ],
    )


def test_literal_reference_detection_recovers_urls_and_author_year_citations() -> None:
    slide = {
        "text": [
            {"t": "Source: https://example."},
            {"t": "org/report and Smith et al. (2024)"},
        ],
        "tables": [],
    }

    assert slide_analyzer.literal_references(slide) == [
        "https://example.org/report",
        "Smith et al. (2024)",
    ]


def test_term_cannot_come_from_model_advice_or_a_caption_guess() -> None:
    result = valid_analysis()
    result["complex_terms"] = [{"term": "ONNX", "definition": "A model exchange format."}]
    slide_analyzer.validate_generated_findings(
        result,
        [
            {
                "num": 1,
                "img_context": "This might describe ONNX.",
                "text": [{"t": "Research"}],
            }
        ],
    )
    assert result["complex_terms"] == []

    result["complex_terms"] = [{"term": "ONNX", "definition": "A model exchange format."}]
    slide_analyzer.validate_generated_findings(result, [{"num": 1, "text": [{"t": "ONNX"}]}])
    assert result["complex_terms"] == [{"term": "ONNX", "definition": "A model exchange format."}]


def test_invalid_or_duplicate_complex_terms_do_not_fail_the_analysis() -> None:
    result = valid_analysis()
    result["complex_terms"] = [
        {"term": "API", "definition": "An interface for software communication."},
        {"term": "API", "definition": "Duplicate definition."},
        {"term": "Invented term", "definition": "Not in the deck."},
    ]
    slide_analyzer.validate_generated_findings(
        result,
        [{"num": 1, "text": [{"t": "The API returns results."}]}],
    )
    assert result["complex_terms"] == [
        {"term": "API", "definition": "An interface for software communication."}
    ]


def test_vision_context_discards_text_claims_missing_from_extracted_text() -> None:
    caption = (
        "The phrase “Thank You” is a large heading. "
        "Below it, the word “FANTUN” appears in black. "
        "Muted shapes occupy two corners."
    )
    slide = {
        "title": "Thank You",
        "text": [{"t": "Thank You"}, {"t": "FOR YOUR ATTENTION"}],
        "tables": [],
    }
    sanitized = slide_analyzer.sanitize_vision_context(caption, slide)
    assert "Thank You" in sanitized
    assert "Muted shapes" in sanitized
    assert "FANTUN" not in sanitized


def test_vision_prompt_requires_density_without_guessing_unextracted_text(
    monkeypatch, tmp_path
) -> None:
    captured = {}

    class CaptionResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": json.dumps({
                "description": "A dense bullet region is visible.", "checks": []})}}]}

    def post(*_args, **kwargs):
        captured.update(kwargs["json"])
        return CaptionResponse()

    image = tmp_path / "slide.png"
    image.write_bytes(b"image")
    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", post)

    slide_analyzer.caption_slide_image(3, image, "WHY WE DIFFERENT?")
    prompt = captured["messages"][0]["content"][1]["text"]
    assert "every visible text region" in prompt
    assert "approximate line count" in prompt
    assert "Never omit a text region" in prompt
    assert "WHY WE DIFFERENT?" in prompt
    for category in (
        "Contrast:",
        "Typography:",
        "Alignment and spacing:",
        "Overlap and clipping:",
        "Hierarchy and reading order:",
        "Visual consistency:",
    ):
        assert category in prompt
    assert "bright yellow text on white" in prompt
    assert "actual local background" in prompt
    assert "4-7" not in prompt
    assert captured["max_tokens"] >= 900


def test_dense_region_is_evidence_not_a_forced_overload_verdict() -> None:
    result = valid_analysis()
    slide = {
        "num": 1,
        "text_regions": [
            {
                "paragraphs": [
                    {
                        "text": (
                            f"This is sentence length explanation number {number} for the audience."
                        )
                    }
                    for number in range(6)
                ]
            }
        ],
    }

    slide_analyzer.apply_deterministic_findings(result, [slide])

    item = result["per_slide"][0]
    assert item["overload"] is False
    assert item["overload_reason"] is None
    assert "6 sentence-length points" in slide_analyzer.deterministic_overload_reason(slide)


@pytest.mark.parametrize("suggestions", [[], ["[LOW] Slide 1: tighten the supporting sentence."]])
def test_clean_slides_and_slide_number_wording_are_accepted(suggestions):
    result = valid_analysis()
    result["per_slide"][0]["improvement_suggestions"] = suggestions
    slide_analyzer.validate_generated_findings(result, [{"num": 1}])
    slide_analyzer.validate_slide_analysis_result(result, [1])
    assert result["per_slide"][0]["improvement_suggestions"] == suggestions


def test_vision_redaction_preserves_visual_context_in_same_sentence():
    result = slide_analyzer.sanitize_vision_context(
        'A small black label “Invented name” sits below a large blue heading.',
        {"text": [{"t": "Actual title"}]},
    )
    assert "Invented name" not in result
    assert "small black label" in result
    assert "large blue heading" in result
    assert "[unverified visual wording]" in result


def test_objective_table_defects_receive_stable_tips() -> None:
    repeated = "personalized coaching and detailed job matching analytics"
    slide = {
        "num": 1,
        "tables": [
            [
                ["Monthly", "Yearly", "Free"],
                ["$6.99", "$83.88 / $69", "$0"],
                [repeated, repeated, "Basic access"],
            ]
        ],
    }

    tips = slide_analyzer.deterministic_table_tips(slide)

    assert any("repeat the same detailed content" in tip for tip in tips)
    assert any("multiple currency amounts" in tip for tip in tips)


def test_ambiguous_table_symbols_receive_stable_tip() -> None:
    tips = slide_analyzer.deterministic_table_tips(
        {
            "tables": [[["Feature", "Product A", "Product B"], ["Matching", "/", "x"]]],
        }
    )

    assert tips == [
        'Replace or define the symbol-only table entries "/", "x"; their meaning is '
        "ambiguous without a legend."
    ]


def test_analysis_prompt_treats_combined_dense_regions_as_overload_evidence() -> None:
    prompt = slide_analyzer.build_analysis_prompt([{"num": 3, "title": "Features"}])
    assert "Six or more sentence-length bullets" in prompt
    assert "multiple competing dense" in prompt


def test_visual_design_checks_share_existing_feedback_without_replacing_content():
    prompt = slide_analyzer.build_analysis_prompt([{"num": 1, "title": "Example"}])
    for category in (
        "1. Contrast:",
        "2. Typography:",
        "3. Alignment and spacing:",
        "4. Overlap and clipping:",
        "5. Hierarchy and reading order:",
        "6. Visual consistency:",
    ):
        assert category in prompt
    assert "never\nreplace those checks" in prompt
    assert "forced 50/50 count" in prompt
    assert "without a maximum count" in prompt
    assert "Proofread every authoritative title" in prompt
    assert "actual local background" in prompt
    assert "severely low contrast, clipping or overlap" in prompt


def test_unbacked_reference_is_filtered_without_retrying_the_whole_analysis(monkeypatch) -> None:
    bad = valid_analysis()
    bad["per_slide"][0]["refs_found"] = ["https://invented.example"]
    attempts = 0

    def post(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return FakeResponse(bad)

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", post)
    result = slide_analyzer.analyze([{"num": 1}])
    assert result["per_slide"][0]["refs_found"] == []
    assert attempts == 1


def test_generation_schema_requires_all_fields_and_excludes_app_metadata() -> None:
    response_format = slide_analyzer.analysis_response_format([1, 2])
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert "generated_agenda" not in schema["properties"]
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["additionalProperties"] is False
    assert schema["properties"]["per_slide"]["minItems"] == 2
    assert schema["properties"]["per_slide"]["maxItems"] == 2
    for definition in schema["$defs"].values():
        assert set(definition["required"]) == set(definition["properties"])
        assert definition["additionalProperties"] is False
    assert schema["$defs"]["SlideAnalysisPayload"]["properties"]["num"]["enum"] == [1, 2]


def test_retry_and_log_identify_field_without_exposing_response(monkeypatch, caplog) -> None:
    bad = valid_analysis()
    bad["per_slide"][0]["refs_found"] = "PRIVATE_CONTENT_MUST_NOT_BE_LOGGED"
    responses = iter([FakeResponse(bad), FakeResponse(valid_analysis())])
    requests = []

    def post(*args, **kwargs):
        requests.append(kwargs["json"])
        return next(responses)

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", post)
    slide_analyzer.analyze([{"num": 1}])
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert "provider" not in requests[0]
    assert "temperature" not in requests[0]
    assert requests[0]["model"] == "openai/gpt-6-luna"
    retry_prompt = requests[1]["messages"][-1]["content"]
    assert "per_slide.0.refs_found: list_type" in retry_prompt
    assert "per_slide.0.refs_found: list_type" in caplog.text
    assert "PRIVATE_CONTENT_MUST_NOT_BE_LOGGED" not in caplog.text + retry_prompt


def test_unexpected_field_names_are_redacted_from_diagnostics() -> None:
    bad = valid_analysis()
    bad["PRIVATE_FIELD_NAME"] = "PRIVATE_VALUE"
    with pytest.raises(ValidationError) as caught:
        slide_analyzer.validate_slide_analysis_result(bad, [1])
    summary = slide_analyzer.analysis_error_summary(caught.value)
    assert summary == "<unexpected-field>: extra_forbidden"
    assert "PRIVATE" not in summary


def test_final_failure_retains_safe_diagnostic(monkeypatch) -> None:
    bad = valid_analysis()
    bad.pop("complex_terms")
    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", lambda *args, **kwargs: FakeResponse(bad))
    with pytest.raises(slide_analyzer.SlideAnalysisGenerationError) as caught:
        slide_analyzer.analyze([{"num": 1}])
    assert caught.value.diagnostic == "complex_terms: missing"
