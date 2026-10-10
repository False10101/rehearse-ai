import type { NormalizedLandmark } from "@mediapipe/tasks-vision";

export type DebugBounds = { x: number; y: number; width: number; height: number };

export type BrowserObservation = {
  person_detected: boolean;
  left_gaze_position?: [number, number];
  right_gaze_position?: [number, number];
  head_yaw?: number;
  debug?: Record<string, DebugBounds>;
};

const LEFT_EYE_REFERENCE_POINTS = [33, 133, 159, 145, 160, 144, 158, 153, 157, 154, 173, 246];
const RIGHT_EYE_REFERENCE_POINTS = [263, 362, 386, 374, 387, 373, 385, 380, 384, 381, 398, 466];
const LEFT_IRIS_POINTS = [468, 469, 470, 471, 472];
const RIGHT_IRIS_POINTS = [473, 474, 475, 476, 477];
const LEFT_EYE_GEOMETRY = { corners: [33, 133], lids: [159, 145] } as const;
const RIGHT_EYE_GEOMETRY = { corners: [263, 362], lids: [386, 374] } as const;

function bounds(landmarks: NormalizedLandmark[], indexes: number[], padding = 0.012): DebugBounds | null {
  const points = indexes.map((index) => landmarks[index]).filter((point): point is NormalizedLandmark => Boolean(point));
  if (!points.length) return null;
  const x = Math.max(0, Math.min(...points.map((point) => point.x)) - padding);
  const y = Math.max(0, Math.min(...points.map((point) => point.y)) - padding);
  const right = Math.min(1, Math.max(...points.map((point) => point.x)) + padding);
  const bottom = Math.min(1, Math.max(...points.map((point) => point.y)) + padding);
  return right > x && bottom > y ? { x, y, width: right - x, height: bottom - y } : null;
}

function irisCentre(landmarks: NormalizedLandmark[], indexes: number[]): [number, number] | null {
  const points = indexes.map((index) => landmarks[index]);
  if (points.some((point) => !point)) return null;
  return [points.reduce((sum, point) => sum + point.x, 0) / points.length, points.reduce((sum, point) => sum + point.y, 0) / points.length];
}

function positionInEye(
  landmarks: NormalizedLandmark[],
  iris: [number, number],
  geometry: { readonly corners: readonly [number, number]; readonly lids: readonly [number, number] },
): [number, number] | null {
  const corners = geometry.corners.map((index) => landmarks[index]);
  const lids = geometry.lids.map((index) => landmarks[index]);
  if (corners.some((point) => !point) || lids.some((point) => !point)) return null;
  const left = Math.min(...corners.map((point) => point.x));
  const right = Math.max(...corners.map((point) => point.x));
  const top = Math.min(...lids.map((point) => point.y));
  const bottom = Math.max(...lids.map((point) => point.y));
  if (right - left < 0.001 || bottom - top < 0.001) return null;
  return [
    Math.min(1, Math.max(0, (iris[0] - left) / (right - left))),
    Math.min(1, Math.max(0, (iris[1] - top) / (bottom - top))),
  ];
}

export function observationFromLandmarks(landmarks: NormalizedLandmark[] | undefined): BrowserObservation {
  if (!landmarks?.length) return { person_detected: false };
  const face = bounds(landmarks, landmarks.map((_, index) => index), 0.02);
  const leftEye = bounds(landmarks, LEFT_EYE_REFERENCE_POINTS);
  const rightEye = bounds(landmarks, RIGHT_EYE_REFERENCE_POINTS);
  const leftIris = irisCentre(landmarks, LEFT_IRIS_POINTS);
  const rightIris = irisCentre(landmarks, RIGHT_IRIS_POINTS);
  const debug: Record<string, DebugBounds> = {};
  if (face) debug.face = face;
  if (leftEye) debug.left_eye = leftEye;
  if (rightEye) debug.right_eye = rightEye;
  const nose = landmarks[1];
  const observation: BrowserObservation = {
    person_detected: true,
    ...(Object.keys(debug).length ? { debug } : {}),
  };
  if (leftEye && rightEye && nose) {
    const leftCentreX = leftEye.x + leftEye.width / 2;
    const rightCentreX = rightEye.x + rightEye.width / 2;
    const eyeMidpointX = (leftCentreX + rightCentreX) / 2;
    const eyeSpan = Math.max(Math.abs(rightCentreX - leftCentreX), 0.001);
    observation.head_yaw = (nose.x - eyeMidpointX) / eyeSpan;
    const leftPosition = leftIris ? positionInEye(landmarks, leftIris, LEFT_EYE_GEOMETRY) : null;
    const rightPosition = rightIris ? positionInEye(landmarks, rightIris, RIGHT_EYE_GEOMETRY) : null;
    if (leftPosition) observation.left_gaze_position = leftPosition;
    if (rightPosition) observation.right_gaze_position = rightPosition;
  }
  return observation;
}
