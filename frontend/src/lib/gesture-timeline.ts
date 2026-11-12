type Moment = { start_seconds: number; end_seconds?: number; duration_seconds: number };

const bodyAreas = [
  { id: "arms", label: "Arms & hands", types: ["arms_crossed", "gesture_box_excursion", "hand_near_face", "hands_clasped_low"] },
  { id: "head", label: "Head", types: ["repeated_head_movement"] },
  { id: "torso", label: "Torso", types: ["repeated_swaying"] },
];

/** Stable body-area rows, independent of which behavior occurs first. */
export function gestureBodyGroups<T extends Moment & { type: string }>(events: T[]) {
  const groups = bodyAreas.map(area => ({
    id: area.id, label: area.label,
    items: events.filter(event => area.types.includes(event.type)),
  }));
  const other = events.filter(event => !bodyAreas.some(area => area.types.includes(event.type)));
  if (other.length) groups.push({ id: "other", label: "Other movements", items: other });
  return groups;
}

/** Code decisions, not generated wording, determine which issues are displayed. */
export function gestureNeedsAdjustment(event: { detection?: { is_issue?: boolean } | null }) {
  return event.detection?.is_issue === true;
}

/** Preserve each saved moment, including simultaneous and closely spaced ones. */
export function gestureMarkers<T extends Moment>(events: T[], end: number, width: number) {
  const laneEnds: number[] = [];
  const markers = [...events].sort((a, b) => a.start_seconds - b.start_seconds).map(item => {
    const left = item.start_seconds / end * width;
    const span = item.end_seconds === undefined ? item.duration_seconds
      : item.end_seconds - item.start_seconds;
    const markerWidth = Math.max(0, span / end * width);
    const hitWidth = Math.max(44, markerWidth);
    let lane = laneEnds.findIndex(last => last + 12 <= left);
    if (lane < 0) lane = laneEnds.length;
    laneEnds[lane] = left + Math.max(hitWidth, 60);
    return { item, left, width: markerWidth, hitWidth,
      leftPercent: item.start_seconds / end * 100,
      widthPercent: Math.max(0, span / end * 100), lane };
  });
  return { markers, lanes: laneEnds.length };
}

/** Use real clock boundaries so the one-minute point is explicitly labelled. */
export function gestureTicks(end: number) {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600];
  const step = steps.find(value => value >= end / 5) ?? Math.ceil(end / 5 / 3600) * 3600;
  const times = [];
  for (let second = 0; second < end; second += step) times.push(second);
  if (times.length > 1 && end - times[times.length - 1] < step * 0.35) times.pop();
  times.push(end);
  return times.map(seconds => ({ seconds, leftPercent: seconds / end * 100 }));
}
