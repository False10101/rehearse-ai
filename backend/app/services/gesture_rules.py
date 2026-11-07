"""Deterministic delivery checks. No provider or generated text participates here.

Durations are sampled positive evidence, not elapsed time across dropouts. These
are configurable engineering heuristics, not universal rules about body language.
"""

from collections import Counter

RULE_VERSION = "gesture-rules-v3"


def pattern_key(event: dict) -> tuple:
    samples = event.get("measurements") or []
    kind = event.get("type")
    if kind in {"arms_crossed", "hand_near_face", "gesture_box_excursion"}:
        return (kind, _most_common(samples, "posture", ""),
                _most_common(samples, "body_part", ""))
    return (kind,)

# (sustained seconds, repeated episode minimum seconds, episodes, recurrence window)
# Short illustrative reaches and brief comfortable rests are not faults by default.
RULE_LIMITS = {
    "arms_crossed": (1.0, 0.4, 2, 30.0),
    "gesture_box_excursion": (1.2, 0.4, 2, 20.0),
    "hands_clasped_low": (3.0, 0.8, 3, 20.0),
    "hand_near_face": (1.2, 0.6, 2, 30.0),
    # These candidates already require measured direction reversals and extent.
    "repeated_head_movement": (0.4, 0.4, 1, 5.0),
    "repeated_swaying": (0.8, 0.8, 1, 8.0),
}


def rule_decision(event: dict, events: list[dict]) -> dict:
    kind = event.get("type")
    limits = RULE_LIMITS.get(kind)
    if limits is None:
        return {"version": RULE_VERSION, "is_issue": False, "reason": "unsupported_pattern"}
    held, episode_min, required, window = limits
    duration = float(event.get("duration_seconds", 0))
    nearby = [item for item in events if pattern_key(item) == pattern_key(event)
              and abs(float(item.get("start_seconds", 0)) - event["start_seconds"]) <= window
              and float(item.get("duration_seconds", 0)) + 1e-6 >= episode_min]
    repeated = len(nearby) >= required and duration + 1e-6 >= episode_min
    sustained = duration + 1e-6 >= held
    return {
        "version": RULE_VERSION, "is_issue": sustained or repeated,
        "reason": "measured_repeated_movement" if kind in {
            "repeated_head_movement", "repeated_swaying"
        } else "sustained_posture" if sustained else "recurrent_posture" if repeated
        else "brief_isolated_movement",
        "observed_seconds": round(duration, 2), "nearby_episodes": len(nearby),
        "window_seconds": window, "sustained_threshold_seconds": held,
    }


def _most_common(samples: list[dict], key: str, default: str) -> str:
    values = [sample[key] for sample in samples if sample.get(key)]
    return Counter(values).most_common(1)[0][0] if values else default


def measured_coaching(event: dict) -> dict:
    """Render observations from actual recorded facts, never from an LLM verdict."""
    kind = event["type"]
    samples = event.get("measurements") or []
    body = _most_common(samples, "body_part", "your arm")
    posture = _most_common(samples, "posture", "across your torso")
    axis = _most_common(samples, "axis", "side to side")
    duration = float(event.get("duration_seconds", 0))
    duration_text = f"{duration:g} {'second' if duration == 1 else 'seconds'}"
    evidence = event.get("detection") or {}
    episodes = int(evidence.get("nearby_episodes", 1))
    # Count distinct observed turning points inside this actual event, not the
    # maximum count of a sliding recognition window that may precede the card.
    turns_by_axis: dict[str, set] = {}
    for sample in samples:
        turns = turns_by_axis.setdefault(sample.get("axis", ""), set())
        turns.update(round(float(t), 3) for t in sample.get("reversal_seconds", [])
                     if event["start_seconds"] <= float(t) <= event["end_seconds"])
    repeats = max((len(turns) for turns in turns_by_axis.values()), default=0)
    if repeats:
        axis = max(turns_by_axis, key=lambda key: len(turns_by_axis[key])) or axis
    text = {
        "arms_crossed": (
            "Release the crossed arm between points",
            f"You kept {body} {posture} for about {duration_text} in this passage.",
            "Holding this position leaves less room for your hands to support your explanation.",
            "Release the arm after this point and let your hands return to a comfortable rest.",
        ),
        "gesture_box_excursion": (
            "Bring the extended arm back after the emphasis",
            f"You held {body} nearly straight out to the side for about {duration_text}.",
            "A reach held after the emphasis can draw attention away from the next point.",
            "Complete the reach with the word it emphasizes, then bring the arm back.",
        ),
        "hands_clasped_low": (
            "Release the low hand clasp between ideas",
            f"Your hands stayed close together low on your torso for about {duration_text}.",
            "A prolonged clasp keeps both hands occupied instead of available for emphasis.",
            "Release the clasp for the next key idea, then use a comfortable resting position.",
        ),
        "hand_near_face": (
            "Finish the face-level adjustment before continuing",
            f"You kept {body.replace('arm', 'hand')} near your face for about "
            f"{duration_text} during this passage.",
            "A lingering or repeated face-level hand movement competes with your explanation.",
            "Finish the adjustment, lower the hand, and continue the next sentence "
            "with it relaxed.",
        ),
        "repeated_head_movement": (
            "Settle your head between points",
            f"Your head moved {axis} repeatedly"
            + (f", changing direction at least {repeats} times in this passage." if repeats
               else f" for about {duration_text} in this passage."),
            "Repeated back-and-forth movement can compete with the point you are delivering.",
            "Finish the sentence with your head settled, then turn deliberately "
            "for the next point.",
        ),
        "repeated_swaying": (
            "Settle your weight before the next point",
            "Your torso shifted from side to side repeatedly"
            + (f", changing direction at least {repeats} times in this passage." if repeats
               else f" for about {duration_text} in this passage."),
            "Repeated shifts can draw attention away from an otherwise steady explanation.",
            "Balance your weight comfortably while finishing this idea; move at the transition.",
        ),
    }
    title, observation, impact, recommendation = text[kind]
    if episodes >= 2 and kind not in {"repeated_head_movement", "repeated_swaying"}:
        observation += f" The same pattern occurred {episodes} times nearby."
    return {
        "assessment": "adjustment", "source": "code", "version": RULE_VERSION,
        "title": title, "observation": observation, "impact": impact,
        "recommendation": recommendation,
        "evidence_seconds": [float(event.get("evidence_seconds", event["start_seconds"]))],
    }


def prepare_gesture_events(events: list[dict]) -> list[dict]:
    """Legacy AI assessments are deliberately ignored; only measured rules filter."""
    events = [event for event in events if isinstance(event, dict)]
    prepared = []
    for original in events:
        event = {**original}
        decision = rule_decision(event, events)
        if not decision["is_issue"]:
            continue
        event["detection"] = decision
        coaching = measured_coaching(event)
        polished = event.get("coaching")
        polished = polished if isinstance(polished, dict) else {}
        if polished.get("version") == RULE_VERSION and polished.get("source") == "rewrite":
            # The model may rewrite advice only, never observations or decisions.
            for key in ("title", "impact", "recommendation"):
                if isinstance(polished.get(key), str) and polished[key].strip():
                    coaching[key] = polished[key]
            coaching["source"] = "rewrite"
        event["coaching"] = coaching
        prepared.append(event)
    return prepared
