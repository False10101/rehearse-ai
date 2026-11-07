# MediaPipe runtime assets

These files are served locally so Live Practice does not depend on a third-party CDN at runtime.

- WASM runtime: `@mediapipe/tasks-vision` 1.0.1, Apache-2.0
- Face model: MediaPipe Face Landmarker float16, version 1
- Model source: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`

When the package version changes, copy its complete `wasm/` directory here and retest the live landmark pipeline.

- Pose model: MediaPipe Pose Landmarker Lite float16, version 1
  - Source: https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
- Hand model: MediaPipe Hand Landmarker float16, version 1
  - Source: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task

Live Practice runs face/iris inference on camera updates and pose/hand inference
at up to 5 Hz. All models run in the browser. Only numerical landmarks are sent
to the session tracker; camera frames are not uploaded or saved.
