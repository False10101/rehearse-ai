import assert from "node:assert/strict";
import test from "node:test";
import type { NormalizedLandmark } from "@mediapipe/tasks-vision";

import { observationFromLandmarks } from "./live-observation.ts";

const LEFT_EYE = [33, 133, 159, 145, 160, 144, 158, 153, 157, 154, 173, 246];
const RIGHT_EYE = [263, 362, 386, 374, 387, 373, 385, 380, 384, 381, 398, 466];
const LEFT_IRIS = [468, 469, 470, 471, 472];
const RIGHT_IRIS = [473, 474, 475, 476, 477];

function centredFace(): NormalizedLandmark[] {
  const point = (x: number, y: number): NormalizedLandmark => ({ x, y, z: 0, visibility: 1 });
  const landmarks = Array.from({ length: 478 }, () => point(0.5, 0.5));
  landmarks[1] = point(0.5, 0.46);
  LEFT_EYE.forEach((index, point) => {
    landmarks[index] = { x: point % 2 ? 0.37 : 0.33, y: point % 3 ? 0.48 : 0.52, z: 0, visibility: 1 };
  });
  RIGHT_EYE.forEach((index, point) => {
    landmarks[index] = { x: point % 2 ? 0.67 : 0.63, y: point % 3 ? 0.48 : 0.52, z: 0, visibility: 1 };
  });
  LEFT_IRIS.forEach((index) => { landmarks[index] = point(0.35, 0.5); });
  RIGHT_IRIS.forEach((index) => { landmarks[index] = point(0.65, 0.5); });
  return landmarks;
}

test("returns no-person observation when face landmarks are absent", () => {
  assert.deepEqual(observationFromLandmarks(undefined), { person_detected: false });
});

test("derives centred gaze, head yaw, and debug bounds", () => {
  const observation = observationFromLandmarks(centredFace());

  assert.equal(observation.person_detected, true);
  assert.ok(observation.head_yaw !== undefined);
  assert.ok(Math.abs(observation.head_yaw) < 0.01);
  assert.ok(observation.left_gaze_position);
  assert.ok(observation.right_gaze_position);
  assert.ok(Math.abs(observation.left_gaze_position[0] - 0.5) < 0.01);
  assert.ok(Math.abs(observation.right_gaze_position[0] - 0.5) < 0.01);
  assert.ok(observation.debug?.face);
  assert.ok(observation.debug?.left_eye);
  assert.ok(observation.debug?.right_eye);
});

test("keeps face tracking available when iris landmarks are unavailable", () => {
  const landmarks = centredFace().slice(0, 468);
  const observation = observationFromLandmarks(landmarks);

  assert.equal(observation.person_detected, true);
  assert.equal(observation.left_gaze_position, undefined);
  assert.equal(observation.right_gaze_position, undefined);
  assert.ok(observation.head_yaw !== undefined);
});

test("uses anatomical eye geometry instead of padded debug bounds", () => {
  const landmarks = centredFace();
  LEFT_IRIS.forEach((index) => { landmarks[index] = { x: 0.365, y: 0.5, z: 0, visibility: 1 }; });
  RIGHT_IRIS.forEach((index) => { landmarks[index] = { x: 0.665, y: 0.5, z: 0, visibility: 1 }; });

  const observation = observationFromLandmarks(landmarks);

  assert.ok(observation.left_gaze_position);
  assert.ok(observation.right_gaze_position);
  assert.ok(observation.left_gaze_position[0] > 0.8);
  assert.ok(observation.right_gaze_position[0] > 0.8);
});

test("keeps both eye measurements separate when they disagree", () => {
  const landmarks = centredFace();
  LEFT_IRIS.forEach((index) => { landmarks[index] = { x: 0.335, y: 0.5, z: 0, visibility: 1 }; });
  RIGHT_IRIS.forEach((index) => { landmarks[index] = { x: 0.665, y: 0.5, z: 0, visibility: 1 }; });

  const observation = observationFromLandmarks(landmarks);

  assert.ok(observation.left_gaze_position);
  assert.ok(observation.right_gaze_position);
  assert.ok(observation.left_gaze_position[0] < 0.2);
  assert.ok(observation.right_gaze_position[0] > 0.8);
});

test("derives horizontal head yaw independently from iris gaze", () => {
  const landmarks = centredFace();
  landmarks[1] = { x: 0.56, y: 0.46, z: 0, visibility: 1 };

  const observation = observationFromLandmarks(landmarks);

  assert.ok(observation.head_yaw !== undefined);
  assert.ok(observation.head_yaw > 0.18);
  assert.ok(observation.left_gaze_position);
  assert.ok(observation.right_gaze_position);
  assert.ok(Math.abs(observation.left_gaze_position[0] - 0.5) < 0.01);
});
