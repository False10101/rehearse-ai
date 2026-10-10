# MediaPipe runtime assets

These files are served locally so Live Practice does not depend on a third-party CDN at runtime.

- WASM runtime: `@mediapipe/tasks-vision` 1.0.1, Apache-2.0
- Face model: MediaPipe Face Landmarker float16, version 1
- Model source: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`

When the package version changes, copy its complete `wasm/` directory here and retest the live landmark pipeline.
