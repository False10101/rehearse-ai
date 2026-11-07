import type { Matrix, NormalizedLandmark } from "@mediapipe/tasks-vision";

export type DebugBounds = { x: number; y: number; width: number; height: number };

export type LandmarkPoint = [number, number, number, number];
export type BrowserObservation = {
  person_detected: boolean;
  eyes?: [number, number, number, number];
  head?: [number, number, number];
  face_targets?: [number, number][];
  body?: LandmarkPoint[];
  hands?: LandmarkPoint[][];
  body_updated: boolean;
  hands_updated: boolean;
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
  if (right - left < 0.001 || (bottom - top) / (right - left) < 0.12) return null;
  // Eyelids follow vertical eye movement, so their changing opening is a poor
  // denominator for up/down gaze. Anchor to the corner line and eye width.
  const [first, second] = corners[0].x <= corners[1].x ? corners : [corners[1], corners[0]];
  const fractionAcross = (iris[0] - left) / (right - left);
  const cornerLineY = first.y + fractionAcross * (second.y - first.y);
  return [
    Math.min(1, Math.max(0, fractionAcross)),
    Math.min(1, Math.max(0, 0.5 + 2.5 * (iris[1] - cornerLineY) / (right - left))),
  ];
}

function pack(points: NormalizedLandmark[]): LandmarkPoint[] {
  return points.map((p) => [p.x, p.y, p.z, p.visibility ?? 1]);
}

export function observationFromLandmarks(
  landmarks: NormalizedLandmark[] | undefined,
  pose?: Matrix,
  body?: NormalizedLandmark[],
  hands?: NormalizedLandmark[][],
  bodyUpdated = true,
  handsUpdated = true,
): BrowserObservation {
  const observation: BrowserObservation = {
    person_detected: Boolean(landmarks?.length),
    body_updated: bodyUpdated,
    hands_updated: handsUpdated,
    ...(body ? { body: pack(body) } : {}),
    ...(hands ? { hands: hands.map(pack) } : {}),
  };
  if (!landmarks?.length) return observation;
  const face = bounds(landmarks, landmarks.map((_, index) => index), 0.02);
  const leftEye = bounds(landmarks, LEFT_EYE_REFERENCE_POINTS);
  const rightEye = bounds(landmarks, RIGHT_EYE_REFERENCE_POINTS);
  const debug: Record<string, DebugBounds> = {};
  if (face) debug.face = face;
  if (leftEye) debug.left_eye = leftEye;
  if (rightEye) debug.right_eye = rightEye;
  observation.debug = debug;
  // Canonical-to-camera matrix, column-major. Positive camera x is the
  // presenter's left; positive y is up. Roll is around the face-forward axis.
  if (pose?.rows === 4 && pose.columns === 4 && pose.data.length === 16 && pose.data.every(Number.isFinite)) {
    const [x, y, z] = [pose.data[8], pose.data[9], pose.data[10]];
    if (Math.hypot(x, y, z) > 0.001) {
      observation.head = [
        Math.atan2(x, z) * 180 / Math.PI,
        Math.atan2(y, Math.hypot(x, z)) * 180 / Math.PI,
        Math.atan2(pose.data[1], pose.data[0]) * 180 / Math.PI,
      ];
    }
  }
  const leftIris = irisCentre(landmarks, LEFT_IRIS_POINTS);
  const rightIris = irisCentre(landmarks, RIGHT_IRIS_POINTS);
  const left = leftIris ? positionInEye(landmarks, leftIris, LEFT_EYE_GEOMETRY) : null;
  const right = rightIris ? positionInEye(landmarks, rightIris, RIGHT_EYE_GEOMETRY) : null;
  if (left && right && [...left, ...right].every(Number.isFinite)) observation.eyes = [...left, ...right];
  if ([13, 33, 263, 10].every((i) => landmarks[i])) {
    observation.face_targets = [13, 33, 263, 10].map((i) => [landmarks[i].x, landmarks[i].y]);
  }
  return observation;
}
