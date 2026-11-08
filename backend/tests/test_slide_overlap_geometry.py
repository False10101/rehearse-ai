from app.services.slide_design import overlap_candidates, _intersection_area


def slide(corners, blocker, **own):
    region = {"region": 2, "left": 0, "top": 0, "width": 10, "height": 10,
              "paragraphs": [{"text": "Label"}], "slide_corners": corners}
    return {"text_regions": [region], "shape_evidence": [
        {"z_order": 2, "fill_color": None, "coordinate_scope": "group", "rotation": 30,
         **region, **own}, blocker]}


def test_grouped_rotated_text_and_cover_are_not_skipped():
    corners = [[5, 0], [10, 5], [5, 10], [0, 5]]
    cover = {"z_order": 3, "fill_color": "#000000", "coordinate_scope": "group",
             "rotation": 45, "left": 0, "top": 0, "width": 10, "height": 10,
             "slide_corners": corners}
    result = overlap_candidates(slide(corners, cover))
    assert len(result) == 1
    assert result[0]["box_overlap_fraction"] == 1
    assert result[0]["status"] == "candidate_requires_visual_confirmation"


def test_flipped_corner_order_keeps_same_intersection():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    diamond = [[5, 0], [10, 5], [5, 10], [0, 5]]
    assert _intersection_area(square, diamond) == 50
    assert _intersection_area(square, list(reversed(diamond))) == 50


def test_intersecting_bounding_boxes_do_not_prove_polygon_overlap():
    # Two thin diagonal rectangles: their bounding boxes intersect, their polygons do not.
    first = [[0, 0], [10, 10], [9, 11], [-1, 1]]
    second = [[0, 4], [6, 10], [5, 11], [-1, 5]]
    assert _intersection_area(first, second) == 0


def test_earlier_unfilled_line_is_a_candidate_but_background_panel_is_not():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    earlier = {"z_order": 1, "fill_color": None, "raw_geometry": "line",
               "line": {"head_end": {"type": "triangle"}},
               "left": 5, "top": 5, "width": 10, "height": 10}
    result = overlap_candidates(slide(square, earlier))
    assert result[0]["drawn_before_text"] is True
    assert result[0]["box_overlap_fraction"] == .25
    background = {**earlier, "raw_geometry": "rect", "line": None, "fill_color": "#EEEEEE"}
    assert overlap_candidates(slide(square, background)) == []


def test_touching_edges_do_not_create_overlap():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    other = [[10, 0], [20, 0], [20, 10], [10, 10]]
    assert _intersection_area(square, other) == 0


def test_zero_width_line_crossing_text_is_not_lost_by_area_test():
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    line = {"z_order": 3, "fill_color": None, "raw_geometry": "line",
            "left": 5, "top": -5, "width": 0, "height": 20,
            "line": {"slide_endpoints": [[5, -5], [5, 15]]}}
    assert len(overlap_candidates(slide(square, line))) == 1
    outside = {**line, "left": 15,
               "line": {"slide_endpoints": [[15, -5], [15, 15]]}}
    assert overlap_candidates(slide(square, outside)) == []
