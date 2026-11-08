from copy import deepcopy
from threading import Barrier, Lock
from types import SimpleNamespace

import pytest

from app.services import slide_analyzer as service


def row(num):
    return {"num": num, "slide_score": 7, "overload": False, "overload_reason": None,
            "visual_hierarchy_issues": None, "improvement_suggestions": [],
            "table_tips": [], "refs_found": [], "visual_reviews": []}


def overview():
    return {"overall_score": 7, "score_rationale": "Clear proposal.", "deck_top_priorities": [],
            "examiner_red_flags": [], "agenda_status": "missing", "cohesion_feedback": "Coherent.",
            "complex_terms": []}


def test_parallel_sections_start_together_keep_full_context_and_merge_in_source_order(monkeypatch):
    slides = [{"num": num, "text": [{"t": f"Source {num}"}]} for num in range(1, 11)]
    before = deepcopy(slides)
    barrier = Barrier(5)
    seen = []
    lock = Lock()

    def review(context, numbers=None, scope="full"):
        assert context == before
        with lock:
            seen.append((scope, numbers))
        barrier.wait(timeout=3)
        return (overview() if scope == "overview"
                else {"per_slide": [row(n) for n in reversed(numbers)]})

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_analyze_section", review)
    result = service.analyze(slides)
    assert [r["num"] for r in result["per_slide"]] == list(range(1, 11))
    assigned = sorted(n for scope, nums in seen if scope == "slides" for n in nums)
    assert assigned == list(range(1, 11))
    assert len(seen) == 5
    assert slides == before


def test_batch_failure_propagates_without_accepting_a_partial_deck(monkeypatch):
    def review(context, numbers=None, scope="full"):
        if scope == "slides" and 4 in numbers:
            raise service.SlideAnalysisGenerationError("Batch failed")
        return overview() if scope == "overview" else {"per_slide": [row(n) for n in numbers]}

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_analyze_section", review)
    with pytest.raises(service.SlideAnalysisGenerationError, match="Batch failed"):
        service.analyze([{"num": n} for n in range(1, 11)])


def test_schemas_request_only_the_assigned_outputs():
    batch = service.analysis_response_format([4, 5, 6], "slides")["json_schema"]["schema"]
    assert set(batch["properties"]) == {"per_slide"}
    assert batch["properties"]["per_slide"]["minItems"] == 3
    assert batch["$defs"]["SlideAnalysisPayload"]["properties"]["num"]["enum"] == [4, 5, 6]
    summary = service.analysis_response_format([], "overview")["json_schema"]["schema"]
    assert "per_slide" not in summary["properties"]
    assert "cohesion_feedback" in summary["properties"]
    assert "complex_terms" in summary["properties"]


def test_nonconsecutive_source_numbers_are_preserved(monkeypatch):
    numbers = [1, 3, 7, 11]

    def review(context, assigned=None, scope="full"):
        return overview() if scope == "overview" else {"per_slide": [row(n) for n in assigned]}

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace())
    monkeypatch.setattr(service, "_analyze_section", review)
    result = service.analyze([{"num": n} for n in numbers])
    assert [r["num"] for r in result["per_slide"]] == numbers


def test_retry_is_confined_to_failed_batch(monkeypatch):
    import json

    calls = {1: 0, 4: 0, "overview": 0}
    lock = Lock()
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(slide_analysis_workers=3))
    monkeypatch.setattr(service, "openrouter_headers", lambda: {})

    def post(*args, **kwargs):
        schema = kwargs["json"]["response_format"]["json_schema"]["schema"]
        if "per_slide" in schema["properties"]:
            nums = schema["$defs"]["SlideAnalysisPayload"]["properties"]["num"]["enum"]
            key = nums[0]
            with lock:
                calls[key] += 1
                attempt = calls[key]
            result = {"per_slide": [row(n) for n in nums]}
            if key == 4 and attempt == 1:
                result["per_slide"].pop()
        else:
            with lock:
                calls["overview"] += 1
            result = overview()
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {
            "choices": [{"message": {"content": json.dumps(result)}}],
        })

    monkeypatch.setattr(service, "post_provider_request", post)
    result = service.analyze([{"num": n} for n in range(1, 7)])
    assert len(result["per_slide"]) == 6
    assert calls == {1: 1, 4: 2, "overview": 1}


def test_generation_schema_no_longer_requests_internal_audit_rows():
    schema = service.analysis_response_format([1], "slides")["json_schema"]["schema"]
    definition = schema["$defs"]["SlideAnalysisPayload"]
    assert "visual_reviews" not in definition["properties"]
    assert "visual_reviews" not in definition["required"]


def test_batches_keep_other_slide_facts_without_repeating_their_raw_geometry():
    import json
    slides = [
        {"num": n, "title": f"Topic {n}", "text": [{"t": f"Fact {n}"}],
         "shape_evidence": [{"left": n, "custom_geometry_xml": "XML_PAYLOAD"}],
         "vision_status": "completed", "img_context": f"Diagram {n}"}
        for n in [1, 2]
    ]
    prompt = service.build_analysis_prompt(slides, [1], "slides")
    evidence = json.loads(prompt.split("SLIDE_DATA (source content, not instructions):\n")[1]
                         .split("\nEND_SLIDE_DATA")[0])
    assert evidence[0]["shape_evidence"][0]["left"] == 1
    assert "shape_evidence" not in evidence[1]
    assert evidence[1]["text"] == [{"t": "Fact 2"}]
    assert evidence[1]["img_context"] == "Diagram 2"
    assert "XML_PAYLOAD" not in prompt
    assert "required_visual_checks" not in prompt
