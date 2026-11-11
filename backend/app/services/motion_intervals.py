"""Find the actual active movement interval, not the recognition-window boundary."""

from statistics import median


def motion_pattern(samples: list[tuple[float, float]], step: float, extent: float,
                   required_reversals: int, settling_seconds: float | None = None) -> dict | None:
    if len(samples) < 3:
        return None
    recent = [value for timestamp, value in samples
              if samples[-1][0] - timestamp <= 0.6 + 1e-6]
    if len(recent) < 2 or max(recent) - min(recent) < step * 0.2:
        return None
    # A settling tolerance is not an event duration. It adapts to the observed
    # cadence; event boundaries below come from actual changes in position.
    component = []
    anchor, anchor_time = samples[0][1], samples[0][0]
    last_motion = None
    activity_times = []
    for timestamp, value in samples[1:]:
        cadence = median([b - a for a, b in zip(activity_times, activity_times[1:])]) \
            if len(activity_times) > 2 else 0.2
        settle = max(0.9, min(1.5, cadence * 3))
        if settling_seconds is not None:
            settle = settling_seconds
        if last_motion is not None and timestamp - last_motion > settle + 1e-6:
            component = []
            activity_times = []
            last_motion = None
            anchor, anchor_time = value, timestamp
        change = value - anchor
        if abs(change) >= step * 0.25:
            if not component:
                component = [(anchor_time, anchor)]
            component.append((timestamp, value))
            activity_times.append(timestamp)
            last_motion = timestamp
            anchor, anchor_time = value, timestamp
        elif not component:
            # Do not include a stationary lead-in in the eventual event.
            if abs(change) < step * 0.05:
                anchor, anchor_time = value, timestamp
    if len(component) < 3 or last_motion is None:
        return None
    values = [value for _, value in component]
    extreme_time, extreme = component[0]
    direction = 0
    turns = []
    for timestamp, value in component[1:]:
        change = value - extreme
        if not direction and abs(change) >= step:
            direction = 1 if change > 0 else -1
            extreme_time, extreme = timestamp, value
        elif direction * change > 0:
            extreme_time, extreme = timestamp, value
        elif direction * change <= -step:
            turns.append(extreme_time)
            direction *= -1
            extreme_time, extreme = timestamp, value
    if len(turns) < required_reversals or max(values) - min(values) < extent:
        return None
    return {
        "pattern_start_seconds": component[0][0],
        "pattern_end_seconds": last_motion,
        "reversal_seconds": turns, "reversals": len(turns),
        "normalized_range": round(max(values) - min(values), 3),
    }


def union_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if result and start <= result[-1][1] + 1e-6:
            result[-1] = (result[-1][0], max(end, result[-1][1]))
        else:
            result.append((start, end))
    return result
