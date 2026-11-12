import assert from "node:assert/strict";
import test from "node:test";
import { gestureBodyGroups, gestureMarkers, gestureNeedsAdjustment, gestureTicks } from "./gesture-timeline.ts";

test("body-area grouping stays ordered and preserves different simultaneous arm behaviors", () => {
  const events = ["repeated_swaying", "hands_clasped_low", "repeated_head_movement", "arms_crossed", "hand_near_face", "gesture_box_excursion"]
    .map(type => ({ type, start_seconds: 5, duration_seconds: 2 }));
  const groups = gestureBodyGroups(events);
  assert.deepEqual(groups.map(group => group.label), ["Arms & hands", "Head", "Torso"]);
  assert.equal(groups[0].items.length, 4);
  assert.equal(gestureMarkers(groups[0].items, 60, 600).markers.length, 4);
  assert.equal(gestureMarkers(groups[0].items, 60, 600).lanes, 4);
  assert.equal(groups.flatMap(group => group.items).length, events.length);
  assert.equal(events[0].type, "repeated_swaying");
});

test("missing body areas retain their rows and unknown detections are not lost", () => {
  const groups = gestureBodyGroups([{ type: "new_behavior", start_seconds: 2, duration_seconds: 1 }]);
  assert.deepEqual(groups.map(group => group.id), ["arms", "head", "torso", "other"]);
  assert.ok(groups.slice(0, 3).every(group => group.items.length === 0));
  assert.equal(groups[3].items[0].type, "new_behavior");
});

test("issue timeline follows code decisions, never an AI verdict or wording availability", () => {
  const events = [
    { detection: { is_issue: false }, coaching: { assessment: "adjustment" } },
    { detection: { is_issue: true }, coaching: { assessment: "appropriate" } },
    { detection: { is_issue: true }, coaching: null }, {},
  ];
  assert.deepEqual(events.filter(gestureNeedsAdjustment), [events[1], events[2]]);
});

test("markers remain chronological without mutating the report", () => {
  const events = [{ start_seconds: 20, duration_seconds: 2 }, { start_seconds: 5, duration_seconds: 3 }];
  const result = gestureMarkers(events, 60, 600);
  assert.deepEqual(result.markers.map(marker => marker.item.start_seconds), [5, 20]);
  assert.equal(events[0].start_seconds, 20);
  assert.equal(result.markers[0].left, 50);
});

test("short and simultaneous events remain separate clickable markers", () => {
  const events = [0, 0, 1, 20].map(start_seconds => ({ start_seconds, duration_seconds: 0.4 }));
  const { markers, lanes } = gestureMarkers(events, 60, 600);
  assert.equal(markers.length, 4);
  assert.equal(lanes, 3);
  assert.deepEqual(markers.map(marker => marker.lane), [0, 1, 2, 0]);
  assert.ok(markers.every(marker => marker.hitWidth >= 44));
  assert.ok(markers.every(marker => marker.width === 4));
});

test("long intervals retain their measured width and empty reports create no markers", () => {
  assert.equal(gestureMarkers([{ start_seconds: 10, duration_seconds: 20 }], 60, 600).markers[0].width, 200);
  assert.deepEqual(gestureMarkers([], 60, 600), { markers: [], lanes: 0 });
});

test("timeline uses actual event boundaries, not just counted positive samples", () => {
  const event = { start_seconds: 5, end_seconds: 15, duration_seconds: 7 };
  assert.equal(gestureMarkers([event], 60, 600).markers[0].width, 100);
});

test("late events share the axis scale at narrow and wide plot sizes", () => {
  const event = { start_seconds: 90, end_seconds: 100, duration_seconds: 10 };
  const narrow = gestureMarkers([event], 120, 600).markers[0];
  const wide = gestureMarkers([event], 120, 1200).markers[0];
  assert.equal(narrow.leftPercent, 75);
  assert.equal(wide.leftPercent, 75);
  assert.equal(narrow.widthPercent, wide.widthPercent);
  assert.equal(narrow.left, 450);
  assert.equal(wide.left, 900);
});

test("axis labels clock boundaries and includes the full recording endpoint", () => {
  const end = 116.266667;
  const ticks = gestureTicks(end);
  assert.deepEqual(ticks.map(tick => tick.seconds), [0, 30, 60, 90, end]);
  assert.equal(ticks[2].leftPercent, 60 / end * 100);
  assert.equal(ticks.at(-1)?.leftPercent, 100);
  assert.deepEqual(gestureTicks(91).map(tick => tick.seconds), [0, 30, 60, 91]);
});
