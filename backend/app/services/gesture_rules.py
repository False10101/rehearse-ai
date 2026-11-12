"""Deterministic delivery checks. No provider or generated text participates here.

Durations are sampled positive evidence, not elapsed time across dropouts. These
are configurable engineering heuristics, not universal rules about body language.
"""

from collections import Counter

RULE_VERSION = "gesture-rules-v3"
WORDING_VERSION = "gesture-wording-v5"


def pattern_key(event: dict) -> tuple:
    samples = event.get("measurements") or []
    kind = event.get("type")
    if kind in {"arms_crossed", "hand_near_face"}:
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


def gesture_label(event: dict) -> str:
    """Name only distinctions supported by the stored measurements."""
    kind = event["type"]
    samples = event.get("measurements") or []
    body = _most_common(samples, "body_part", "")
    posture = _most_common(samples, "posture", "")
    axes = {sample.get("axis") for sample in samples if sample.get("axis")}
    if kind == "repeated_swaying":
        if axes == {"torso lean"}:
            return "Repeated upper-body leaning"
        if axes == {"whole-body lateral shifting"}:
            return "Repeated sideways body shifting"
        if axes == {"torso lean", "whole-body lateral shifting"}:
            return "Repeated leaning and sideways shifting"
        return "Repeated body swaying"
    if kind == "repeated_head_movement":
        return {frozenset({"side to side"}): "Repeated head turns",
                frozenset({"up and down"}): "Repeated nodding",
                frozenset({"in sideways tilts"}): "Repeated sideways head tilts"}.get(
                    frozenset(axes), "Repeated head movements")
    if kind == "arms_crossed":
        if posture == "folded across your torso":
            return "Both arms crossed over chest"
        if posture == "toward the opposite shoulder":
            return f"{body.removeprefix('your ').capitalize()} across to opposite shoulder" if body else "Arm across to opposite shoulder"
        return "Arm held across chest"
    if kind == "gesture_box_excursion":
        if len({s.get("body_part") for s in samples if s.get("body_part")}) > 1:
            return "Wide sideways arm reaches"
        return f"{body.removeprefix('your ').capitalize()} extended sideways" if body else "Wide sideways reach"
    if kind == "hand_near_face":
        return f"{body.removeprefix('your ').capitalize()} near face" if body else "Hand near face"
    return "Hands held together in front of body"


def measured_coaching(event: dict) -> dict:
    """Render observations from actual recorded facts, never from an LLM verdict."""
    kind = event["type"]
    samples = event.get("measurements") or []
    body = _most_common(samples, "body_part", "your arm")
    if kind == "gesture_box_excursion" and len(
        {s.get("body_part") for s in samples if s.get("body_part")}
    ) > 1:
        body = "your arms"
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
            "Arm held across chest",
            f"You kept {body} {posture} for about {duration_text} in this passage.",
            "Keeping an arm across your chest limits the hand movements you can use while speaking.",
            "Move your arm away from your chest and let it rest comfortably by your side.",
        ),
        "gesture_box_excursion": (
            "Arm held far out to the side",
            f"You held {body} far out to the side for about {duration_text}.",
            "Keeping an arm stretched far to the side can distract viewers from what you are saying.",
            "Bring your arm closer to your body instead of keeping it stretched out.",
        ),
        "hands_clasped_low": (
            "Hands kept together in front of body",
            f"Your hands stayed close together low on your torso for about {duration_text}.",
            "Keeping your hands together for a long time limits the gestures you can use to explain something.",
            "Separate your hands and let them rest comfortably. Use a hand gesture when it helps explain what you mean.",
        ),
        "hand_near_face": (
            "Hand kept near face",
            f"You kept {body.replace('arm', 'hand')} near your face for about "
            f"{duration_text} during this passage.",
            "A hand moving near your face can distract viewers and make your face harder to see.",
            "Lower your hand away from your face and let it rest comfortably.",
        ),
        "repeated_head_movement": (
            "Repeated head movement",
            f"Your head moved {axis} repeatedly"
            + (f", changing direction at least {repeats} times in this passage." if repeats
               else f" for about {duration_text} in this passage."),
            "Repeated head movements can distract viewers from what you are saying.",
            "Face the audience and reduce repeated head movements while speaking.",
        ),
        "repeated_swaying": (
            "Repeated side-to-side body movement",
            "Your torso shifted from side to side repeatedly"
            + (f", changing direction at least {repeats} times in this passage." if repeats
               else f" for about {duration_text} in this passage."),
            "Repeated side-to-side movement can distract viewers from what you are saying.",
            "Stand comfortably with your weight balanced on both feet rather than repeatedly shifting from side to side.",
        ),
    }
    title, observation, impact, recommendation = text[kind]
    if kind == "arms_crossed":
        if posture == "folded across your torso":
            title = "Arms kept crossed"
            recommendation = "Uncross your arms and let your hands rest comfortably by your sides."
        elif posture == "toward the opposite shoulder":
            title = f"{body.capitalize()} held across to the opposite shoulder"
            recommendation = f"Move {body} away from the opposite shoulder and let it rest by your side."
    elif kind == "gesture_box_excursion":
        title = f"{body.capitalize()} held far out to the side"
        recommendation = f"Bring {body} closer to your body and let it rest instead of keeping it stretched out."
    elif kind == "hand_near_face":
        hand = body.replace("arm", "hand")
        title = f"{hand.capitalize()} kept near your face"
        recommendation = f"Lower {hand} away from your face so viewers can see your face clearly."
    elif kind == "repeated_head_movement":
        axes = {sample.get("axis") for sample in samples if sample.get("axis")}
        variants = {
            "side to side": ("Repeated head turns", "Face the audience in one direction for a few sentences instead of repeatedly turning your head left and right."),
            "up and down": ("Repeated nodding", "Bring your head upright after a nod instead of continuing to nod while speaking."),
            "in sideways tilts": ("Repeated sideways head tilts", "Bring your head back upright rather than repeatedly tipping it toward either shoulder."),
        }
        if len(axes) == 1 and axis in variants:
            title, recommendation = variants[axis]
        elif len(axes) > 1:
            directions = [direction for direction in variants if direction in axes]
            observation = "Your head repeatedly moved " + " and ".join(directions) + f" during this {duration_text} passage."
    elif kind == "repeated_swaying":
        axes = {sample.get("axis") for sample in samples if sample.get("axis")}
        if axes == {"torso lean"}:
            title = "Repeated upper-body leaning"
            observation = "Your upper body repeatedly leaned toward one side and then the other"
            impact = "Repeated leaning can distract viewers from what you are saying."
            recommendation = "Keep your shoulders above your hips rather than repeatedly leaning your upper body left and right."
        elif axes == {"whole-body lateral shifting"}:
            title = "Repeated sideways body movement"
            observation = "Your shoulders and hips repeatedly shifted sideways together"
            impact = "Moving your whole body sideways repeatedly can distract viewers from what you are saying."
            recommendation = "Stand in one position with your weight balanced on both feet instead of repeatedly moving sideways."
        elif axes == {"torso lean", "whole-body lateral shifting"}:
            title = "Repeated leaning and sideways movement"
            observation = "Your upper body repeatedly leaned side to side, and your shoulders and hips also shifted sideways together"
            recommendation = "Keep your shoulders above your hips and your weight balanced on both feet instead of repeatedly leaning and moving sideways."
        else:
            observation = "Your body moved from side to side repeatedly"
        observation += (f", changing direction at least {repeats} times in this passage." if repeats
                        else f" during this {duration_text} passage.")
    if episodes >= 2 and kind not in {"repeated_head_movement", "repeated_swaying"}:
        observation += f" This movement was also detected in {episodes - 1} other nearby " + ("section" if episodes == 2 else "sections") + " of the recording."
    return {
        "assessment": "adjustment", "source": "code", "version": RULE_VERSION,
        "wording_version": WORDING_VERSION,
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
        event["label"] = gesture_label(event)
        event["detection"] = decision
        coaching = measured_coaching(event)
        polished = event.get("coaching")
        polished = polished if isinstance(polished, dict) else {}
        if (polished.get("version") == RULE_VERSION
                and polished.get("wording_version") == WORDING_VERSION
                and polished.get("source") == "rewrite"):
            # The model may rewrite advice only, never observations or decisions.
            for key in ("title", "impact", "recommendation"):
                if isinstance(polished.get(key), str) and polished[key].strip():
                    coaching[key] = polished[key]
            coaching["source"] = "rewrite"
        event["coaching"] = coaching
        prepared.append(event)
    return prepared
