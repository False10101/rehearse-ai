"""Lossless compaction of repeated evidence in the final analysis request."""

from copy import deepcopy


def compact_slide_evidence(slide: dict) -> dict:
    result = deepcopy(slide)
    # Keep check evidence inline. References saved little space on real decks
    # and made the model follow indirection while evaluating individual checks.
    # Untransformed regions sometimes repeat the same rectangle three times.
    # Never simplify grouped/rotated geometry or use rounded comparisons.
    for field in ("text_regions", "table_regions", "shape_evidence"):
        for region in result.get(field, []):
            if region.get("coordinate_scope") != "slide":
                continue
            if not all(key in region for key in ("left", "top", "width", "height")):
                continue
            bounds = {key: region[key] for key in ("left", "top", "width", "height")}
            if region.get("local_bounds") == bounds:
                region.pop("local_bounds")
            x, y, w, h = (bounds[k] for k in ("left", "top", "width", "height"))
            corners = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
            if region.get("slide_corners") == corners:
                region.pop("slide_corners")
    return result
