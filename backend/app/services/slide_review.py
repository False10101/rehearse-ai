"""Named visual checks and reconciliation; candidates are not automatic faults."""

import json

from app.services.slide_design import (
    alignment_evidence,
    deck_style_evidence,
    overlap_candidates,
    typography_evidence,
)


def slide_checks(slide):
    checks = []
    typography = typography_evidence(slide)
    if slide.get("generated_by") != "agenda" and slide.get("text_regions"):
        checks.append(
            {
                "id": "hierarchy",
                "kind": "hierarchy",
                "evidence": {
                    "text_regions": typography,
                    "title": slide.get("title"),
                    "instruction": "Compare prominence with each region's communication role; "
                    "large text alone is not a fault, including on covers and closing slides.",
                },
            }
        )
    for candidate in overlap_candidates(slide):
        checks.append(
            {
                "id": f"overlap-{candidate['text_region']}-{candidate['foreground_shape']}",
                "kind": "overlap",
                "evidence": candidate,
            }
        )
    for group in alignment_evidence(slide):
        checks.append(
            {
                "id": "alignment-" + "-".join(map(str, group["shape_ids"])),
                "kind": "alignment",
                "evidence": group,
            }
        )
    for region in typography:
        if region["readability_review_candidate"]:
            checks.append(
                {"id": f"readability-{region['region']}", "kind": "readability", "evidence": region}
            )
    return checks


def analysis_checks(slides):
    checks = {s["num"]: slide_checks(s) for s in slides}
    styles = deck_style_evidence(slides)
    for profile in styles["profiles"]:
        if not profile["content_comparison_candidate"]:
            continue
        differences = {}
        for field, repeated in styles["repeated_content_styles"].items():
            if profile[field] and profile["num"] not in repeated["supporting_slides"]:
                differences[field] = {"observed": profile[field], **repeated}
        if differences:
            checks[profile["num"]].append(
                {"id": "deck-style", "kind": "style", "evidence": differences}
            )
    return checks


def decode_vision_review(content, checks):
    """Reject malformed/incomplete live output so the caller can retry it."""
    allowed = {c["id"] for c in checks}
    try:
        parsed = json.loads(
            content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        )
    except (ValueError, TypeError) as error:
        raise ValueError("Vision output must be valid JSON.") from error
    if (
        not isinstance(parsed, dict)
        or set(parsed) != {"description", "checks"}
        or not isinstance(parsed.get("description"), str)
        or not parsed["description"].strip()
        or not isinstance(parsed.get("checks"), list)
    ):
        raise ValueError("Vision output requires a nonempty description string and checks array.")
    reviews = []
    seen = set()
    for review in parsed["checks"]:
        if (
            isinstance(review, dict)
            and set(review) == {"check_id", "status", "reason"}
            and review.get("check_id") in allowed
            and review["check_id"] not in seen
            and review.get("status") in {"confirmed", "not_issue", "uncertain"}
            and isinstance(review.get("reason"), str)
            and review["reason"].strip()
        ):
            seen.add(review["check_id"])
            reviews.append(
                {
                    "check_id": review["check_id"],
                    "status": review["status"],
                    "reason": review["reason"],
                }
            )
        else:
            raise ValueError(
                "Vision check has an unknown/duplicate ID, invalid status or empty reason."
            )
    if seen != allowed:
        raise ValueError(f"Vision output must assess all required check IDs: {sorted(allowed)}")
    return parsed["description"].strip(), reviews


def reconcile_reviews(result, slides, checks):
    """Require an explicit disposition, and preserve confirmed fixes in public feedback."""
    for item in result["per_slide"]:
        expected = {c["id"] for c in checks[item["num"]]}
        reviews = item.get("visual_reviews", [])
        ids = [r["check_id"] for r in reviews]
        if set(ids) != expected or len(ids) != len(expected):
            raise ValueError(
                f"Slide {item['num']} must explicitly review each visual check: {sorted(expected)}"
            )
        for review in reviews:
            if review["status"] == "confirmed":
                suggestion = review.get("suggestion")
                if not suggestion or not suggestion.startswith(("[HIGH] ", "[MEDIUM] ", "[LOW] ")):
                    raise ValueError(
                        "Confirmed visual checks require a prioritized actionable suggestion."
                    )
                if suggestion not in item["improvement_suggestions"]:
                    item["improvement_suggestions"].append(suggestion)
        # Preserve the schema-valid audit trail; the UI uses existing feedback fields.
        item["improvement_suggestions"] = list(dict.fromkeys(item["improvement_suggestions"]))
