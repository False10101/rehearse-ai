"""Small geometry helpers for wrist-based hand estimates.

The pose model locates wrists, not fingertips. A bounded forearm continuation
allows the rules to consider the hand beyond its wrist without claiming finger
tracking or exact physical contact.
"""
import math


def hand_segment(points, elbow_index, wrist_index, shoulder_width):
    elbow, wrist = points[elbow_index], points[wrist_index]
    if min(elbow[2], wrist[2]) < 0.5:
        return None
    dx, dy = wrist[0] - elbow[0], wrist[1] - elbow[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return None
    reach = min(length * 0.6, shoulder_width * 0.45)
    return (wrist[:2], (wrist[0] + dx / length * reach, wrist[1] + dy / length * reach))


def point_segment_distance(point, segment):
    start, end = segment
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return math.dist(point[:2], start)
    fraction = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    return math.dist(point[:2], (start[0] + fraction * dx, start[1] + fraction * dy))


def segment_distance(first, second):
    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    a, b = first
    c, d = second
    # Strict crossing; endpoint and collinear cases are covered by distances.
    if cross(a, b, c) * cross(a, b, d) < 0 and cross(c, d, a) * cross(c, d, b) < 0:
        return 0.0
    return min(point_segment_distance(a, second), point_segment_distance(b, second),
               point_segment_distance(c, first), point_segment_distance(d, first))
