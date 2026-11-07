from copy import deepcopy

from app.services.slide_payload import compact_slide_evidence


def test_compaction_keeps_all_checks_and_their_exact_inline_evidence():
    typography = [{"region": 1, "source_text": "Invisible words", "min_font_size_pt": 12}]
    overlap = [{"text_region": 1, "foreground_shape": 3, "coverage_fraction": .8}]
    alignment = [{"shape_ids": [1, 2], "top_spread_fraction": .1}]
    slide = {
        "num": 1, "text": [{"t": "Invisible words"}],
        "typography_review": typography, "overlap_candidates": overlap,
        "alignment_review": alignment,
        "required_visual_checks": [
            {"id": "hierarchy", "evidence": typography},
            {"id": "readability-1", "evidence": typography[0]},
            {"id": "overlap-1-3", "evidence": overlap[0]},
            {"id": "alignment-1-2", "evidence": alignment[0]},
            {"id": "deck-style", "evidence": {"fonts": ["Arial", "Georgia"]}},
        ],
    }
    before = deepcopy(slide)
    compact = compact_slide_evidence(slide)
    assert slide == before
    assert compact["text"] == slide["text"]
    for original, check in zip(slide["required_visual_checks"], compact["required_visual_checks"]):
        assert check["id"] == original["id"]
        assert check["evidence"] == original["evidence"]


def test_only_exactly_redundant_slide_geometry_is_removed():
    plain = {"left": 10, "top": 20, "width": 30, "height": 40,
             "coordinate_scope": "slide", "runs": [{"t": "Text", "sz": 12}],
             "local_bounds": {"left": 10, "top": 20, "width": 30, "height": 40},
             "slide_corners": [[10, 20], [40, 20], [40, 60], [10, 60]]}
    rotated = {**deepcopy(plain), "slide_corners": [[15, 19], [42, 23], [35, 65], [8, 61]]}
    grouped = {**deepcopy(plain), "coordinate_scope": "group", "parent_group_ids": [4]}
    compact = compact_slide_evidence({"text_regions": [plain, rotated, grouped],
                                      "tables": [[['$9 or $99?', 'Unlimited (max 5)']]]})
    assert "local_bounds" not in compact["text_regions"][0]
    assert "slide_corners" not in compact["text_regions"][0]
    assert compact["text_regions"][0]["runs"] == plain["runs"]
    assert compact["text_regions"][1]["slide_corners"] == rotated["slide_corners"]
    assert compact["text_regions"][2] == grouped
    assert compact["tables"] == [[['$9 or $99?', 'Unlimited (max 5)']]]
