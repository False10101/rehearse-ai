import json

import pytest

from app.services.slide_analyzer import apply_deterministic_findings
from app.services.slide_review import decode_vision_review, reconcile_reviews, slide_checks


def test_hierarchy_review_required_even_for_closing_slide():
    slide = {"num": 1, "title": "Closing", "text_regions": [
        {"region": 1, "top": 0, "left": 0, "width": 100, "height": 30,
         "paragraphs": [{"text": "Next action"}],
         "runs": [{"t": "Next action", "sz": 20}]},
        {"region": 2, "top": 100, "left": 0, "width": 100, "height": 30,
         "paragraphs": [{"text": "Slogan"}],
         "runs": [{"t": "Slogan", "sz": 70}]}]}
    checks = slide_checks(slide)
    assert any(c["id"] == "hierarchy" for c in checks)
    agenda_checks = slide_checks({**slide, "generated_by": "agenda"})
    assert not any(c["id"] == "hierarchy" for c in agenda_checks)
    response = {"description": "A closing slide.", "checks": []}
    with pytest.raises(ValueError, match="all required check IDs"):
        decode_vision_review(json.dumps(response), checks)


@pytest.mark.parametrize("kind,bad,good", [
    ("style", "[HIGH] Remove the unrelated recipe.",
     "[MEDIUM] Match the replacement heading font and background to the other content slides."),
    ("hierarchy", "[MEDIUM] Rewrite the next steps with specific actions.",
     "[MEDIUM] Make the slogan smaller so the next steps become the focal point."),
])
def test_visual_advice_is_not_rejected_by_keyword_matching(kind, bad, good):
    check = {"id": kind, "kind": kind}
    review = {"check_id": kind, "status": "confirmed", "reason": "Visible mismatch.",
              "suggestion": bad}
    item = {"num": 1, "visual_reviews": [review], "improvement_suggestions": []}
    reconcile_reviews({"per_slide": [item]}, [{"num": 1}], {1: [check]})
    assert item["improvement_suggestions"] == [bad]
    item["improvement_suggestions"] = []
    review["suggestion"] = good
    reconcile_reviews({"per_slide": [item]}, [{"num": 1}], {1: [check]})
    assert item["improvement_suggestions"] == [good]


def test_valid_hierarchy_does_not_force_a_fault():
    item = {"num": 1, "improvement_suggestions": [], "visual_reviews": [
        {"check_id": "hierarchy", "status": "not_issue",
         "reason": "The prominent title leads naturally into the supporting subtitle.",
         "suggestion": None}]}
    reconcile_reviews({"per_slide": [item]}, [{"num": 1}],
                      {1: [{"id": "hierarchy", "kind": "hierarchy"}]})
    assert item["improvement_suggestions"] == []


def test_alignment_prose_is_not_judged_by_regex():
    check = {"id": "alignment-1-2-3", "kind": "alignment",
             "evidence": {"top_spread_fraction": 0.04}}
    response = {"description": "Three panels.", "checks": [
        {"check_id": check["id"], "status": "not_issue", "reason": "The top edges are aligned."}]}
    assert decode_vision_review(json.dumps(response), [check])[1][0]["status"] == "not_issue"
    response["checks"][0]["reason"] = "Unequal edges distinguish a separate explanatory panel."
    assert decode_vision_review(json.dumps(response), [check])[1][0]["status"] == "not_issue"


def test_readability_advice_does_not_need_specific_keywords():
    check = {"id": "readability-1", "kind": "readability"}
    review = {"check_id": check["id"], "status": "confirmed", "reason": "Dense small body text.",
              "suggestion": "[MEDIUM] Reduce the list to key points."}
    item = {"num": 1, "improvement_suggestions": [], "visual_reviews": [review]}
    reconcile_reviews({"per_slide": [item]}, [{"num": 1}], {1: [check]})
    assert item["improvement_suggestions"] == [review["suggestion"]]
    item["improvement_suggestions"] = []
    review["suggestion"] = "[MEDIUM] Enlarge the body font and provide more line spacing."
    reconcile_reviews({"per_slide": [item]}, [{"num": 1}], {1: [check]})
    assert item["improvement_suggestions"] == [review["suggestion"]]


def test_combined_boundary_fix_replaces_narrow_duplicates(monkeypatch):
    from app.services import slide_analyzer
    monkeypatch.setattr(slide_analyzer, "design_findings", lambda _: [
        '[HIGH] Move “Dependency” inside slide boundaries.',
        '[HIGH] Move “Owner” inside slide boundaries.'])
    combined = '[HIGH] Move Dependency left and Owner up within the slide bounds.'
    item = {"num": 1, "table_tips": [], "visual_hierarchy_issues": None,
            "improvement_suggestions": ['[HIGH] Move Dependency inside.', combined,
                                        '[MEDIUM] Explain Owner responsibilities.']}
    apply_deterministic_findings({"per_slide": [item]}, [{"num": 1}])
    assert item["improvement_suggestions"] == [combined, '[MEDIUM] Explain Owner responsibilities.']


def test_unknown_vision_ids_do_not_become_facts():
    content = json.dumps(
        {
            "description": "A foreground box is visible.",
            "checks": [
                {"check_id": "invented", "status": "confirmed", "reason": "Covered."},
                {
                    "check_id": "overlap-1-2",
                    "status": "confirmed",
                    "reason": "Part of text is covered.",
                },
            ],
        }
    )
    with pytest.raises(ValueError, match="unknown/duplicate"):
        decode_vision_review(content, [{"id": "overlap-1-2"}])
    valid = json.loads(content)
    valid["checks"] = valid["checks"][1:]
    description, reviews = decode_vision_review(json.dumps(valid), [{"id": "overlap-1-2"}])
    assert description == "A foreground box is visible."
    assert len(reviews) == 1
    assert reviews[0]["check_id"] == "overlap-1-2"
    with pytest.raises(ValueError, match="valid JSON"):
        decode_vision_review("Legacy prose caption", [])


def test_omitted_visual_checks_are_not_accepted():
    result = {"per_slide": [{"num": 1, "improvement_suggestions": [], "visual_reviews": []}]}
    with pytest.raises(ValueError, match="explicitly review"):
        reconcile_reviews(result, [{"num": 1}], {1: [{"id": "alignment-1-2-3"}]})


def test_confirmed_vision_overlap_cannot_be_dropped():
    slides = [{"num": 1, "vision_reviews": [{"check_id": "overlap-1-2", "status": "confirmed"}]}]
    item = {
        "num": 1,
        "improvement_suggestions": [],
        "visual_reviews": [
            {
                "check_id": "overlap-1-2",
                "status": "not_issue",
                "reason": "Beginning readable.",
                "suggestion": None,
            }
        ],
    }
    reconcile_reviews({"per_slide": [item]}, slides, {1: [{"id": "overlap-1-2"}]})
    assert item["improvement_suggestions"] == []
    item["visual_reviews"][0].update(status="confirmed", suggestion="[HIGH] Move the covering box.")
    reconcile_reviews({"per_slide": [item]}, slides, {1: [{"id": "overlap-1-2"}]})
    assert item["improvement_suggestions"] == ["[HIGH] Move the covering box."]
    reconcile_reviews({"per_slide": [item]}, slides, {1: [{"id": "overlap-1-2"}]})
    assert len(item["improvement_suggestions"]) == 1


def test_uncertain_size_and_intentional_style_do_not_force_faults():
    item = {
        "num": 1,
        "improvement_suggestions": ["[LOW] Keep the concise summary."],
        "visual_reviews": [
            {
                "check_id": "readability-1",
                "status": "uncertain",
                "reason": "Small footnote.",
                "suggestion": None,
            },
            {
                "check_id": "deck-style",
                "status": "not_issue",
                "reason": "Section change.",
                "suggestion": None,
            },
        ],
    }
    reconcile_reviews(
        {"per_slide": [item]}, [{"num": 1}], {1: [{"id": "readability-1"}, {"id": "deck-style"}]}
    )
    assert len(item["improvement_suggestions"]) == 1


def test_existing_equivalent_table_tips_are_not_repeated():
    tips = [
        "Clarify the price amounts and billing periods.",
        "Define the ambiguous Storage symbols “— / ?”.",
        "Reconcile “Unlimited (max 5)” with the numeric limit.",
    ]
    item = {
        "num": 1,
        "table_tips": tips.copy(),
        "improvement_suggestions": ["[HIGH] Fix pricing."],
        "visual_hierarchy_issues": None,
    }
    apply_deterministic_findings(
        {"per_slide": [item]},
        [{"num": 1, "tables": [[["$9 or $99?", "— / ?", "Unlimited (max 5)"]]]}],
    )
    assert item["table_tips"] == tips


@pytest.mark.parametrize(
    "output",
    [
        {"description": ["Wrong description type"], "checks": []},
        {"description": "", "checks": []},
        {"description": "Visible text", "checks": []},
        {
            "description": "Visible text",
            "checks": [{"check_id": "readability-1", "status": "not_issue", "reason": ""}],
        },
    ],
)
def test_incomplete_vision_output_rejected(output):
    with pytest.raises(ValueError):
        decode_vision_review(json.dumps(output), [{"id": "readability-1"}])


def test_intent_words_do_not_reject_an_entire_response():
    output = {
        "description": "Cards have different widths.",
        "checks": [
            {
                "check_id": "alignment-1-2-3",
                "status": "not_issue",
                "reason": "The staggered layout is intentional.",
            }
        ],
    }
    assert decode_vision_review(json.dumps(output), [{"id": "alignment-1-2-3"}])[1]
    output["checks"][0].update(
        status="uncertain", reason="Different widths are visible; impact unclear."
    )
    assert (
        decode_vision_review(json.dumps(output), [{"id": "alignment-1-2-3"}])[1][0]["status"]
        == "uncertain"
    )


@pytest.mark.parametrize("failure", ["malformed", "truncated"])
def test_http_200_invalid_vision_response_retries(monkeypatch, tmp_path, failure):
    from app.services import slide_analyzer

    image = tmp_path / "slide.png"
    image.write_bytes(b"image")  # No candidates: crop rendering is not needed.
    calls = []

    class Response:
        def raise_for_status(self):
            pass  # HTTP 200 does not imply valid analysis

        def json(self):
            if len(calls) == 1:
                content = (
                    "not JSON"
                    if failure == "malformed"
                    else json.dumps(
                        {"description": "The title says “Invented heading”.", "checks": []}
                    )
                )
                return {
                    "choices": [
                        {
                            "finish_reason": "length" if failure == "truncated" else "stop",
                            "message": {"content": content},
                        }
                    ]
                }
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "description": "A large heading sits above the body.",
                                    "checks": [],
                                }
                            )
                        }
                    }
                ]
            }

    def post(*args, **kwargs):
        calls.append(kwargs["json"]["messages"][0]["content"][1]["text"])
        return Response()

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", post)
    monkeypatch.setattr(slide_analyzer.time, "sleep", lambda _: None)
    _, result = slide_analyzer.caption_slide_image(1, image, "Real heading")
    assert len(calls) == 2
    assert "previous response was rejected" in calls[1]
    assert json.loads(result)["description"] == "A large heading sits above the body."


def test_three_invalid_vision_responses_fail_not_pass_broken_json(monkeypatch, tmp_path, caplog):
    from app.services import slide_analyzer

    image = tmp_path / "slide.png"
    image.write_bytes(b"image")
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "choices": [
                    {"message": {"content": '{"description": ["Wrong type"], "checks": []}'}}
                ]
            }

    def post(*args, **kwargs):
        calls.append(1)
        return Response()

    monkeypatch.setattr(slide_analyzer, "openrouter_headers", lambda: {})
    monkeypatch.setattr(slide_analyzer.requests, "post", post)
    monkeypatch.setattr(slide_analyzer.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="Vision analysis failed"):
        slide_analyzer.caption_slide_image(1, image, "Real heading")
    assert len(calls) == 3
    assert "nonempty description string and checks array" in caplog.text
