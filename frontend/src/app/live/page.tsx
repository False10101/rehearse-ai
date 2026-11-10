"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FaceLandmarker, PoseLandmarker, HandLandmarker, ObjectDetector } from "@mediapipe/tasks-vision";

import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";
import { EndLiveSessionDialog } from "@/components/end-live-session-dialog";
import { LiveRecalibrationHelp } from "@/components/live-recalibration-help";
import { observationFromLandmarks, objectsFromDetections, type DebugBounds } from "@/lib/live-observation";

function SessionControlIcon({ action }: { action: "play" | "pause" | "stop" }) {
  return <svg width="14" height="14" viewBox="4 4 16 16" fill="currentColor" aria-hidden="true" className="block shrink-0">
    {action === "play" ? <path d="M8 5.6c0-.8.9-1.3 1.6-.9l10 6.4a1.1 1.1 0 0 1 0 1.8l-10 6.4c-.7.4-1.6-.1-1.6-.9V5.6Z" /> : action === "pause" ? <><rect x="6" y="5" width="4" height="14" rx="1" /><rect x="14" y="5" width="4" height="14" rx="1" /></> : <rect x="5" y="5" width="14" height="14" rx="2" />}
  </svg>;
}

type Stage = "setup" | "calibrate" | "live" | "paused";
type Permission = "idle" | "requesting" | "granted" | "denied" | "unavailable";
type ConnectionState = "idle" | "connecting" | "connected" | "error";
type SessionNoteTone = "info" | "warning" | "error";

type LiveDebug = {
  face: DebugBounds | null;
  leftEye: DebugBounds | null;
  rightEye: DebugBounds | null;
};

type SessionEvent = {
  id: number;
  kind: string;
  title: string;
  evidence: string;
  startedAtSeconds: number;
  durationSeconds: number;
  active: boolean;
};

type LiveFeedback = {
  status: { eyes: string; head: string; body: string; hands: string };
  prompt: string;
  personDetected: boolean;
  calibrationComplete: boolean;
  calibrationSamples: number;
  calibrationRequired: number;
  debug: LiveDebug | null;
  sessionEvents: SessionEvent[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const debugAvailable = process.env.NODE_ENV !== "production";

function debugBounds(value: unknown): DebugBounds | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (!["x", "y", "width", "height"].every((key) => typeof candidate[key] === "number")) return null;
  return candidate as DebugBounds;
}

function liveDebug(value: unknown): LiveDebug | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  return {
    face: debugBounds(candidate.face),
    leftEye: debugBounds(candidate.left_eye),
    rightEye: debugBounds(candidate.right_eye),
  };
}

function permissionMessage(permission: Permission) {
  if (permission === "requesting") return "Requesting camera access…";
  if (permission === "denied") return "Camera access was blocked. Allow it in your browser settings, then try again.";
  if (permission === "unavailable") return "This browser does not support camera access.";
  if (permission === "granted") return "Camera is on. Start coaching when you’re ready.";
  return "Turn on your camera to get started.";
}

function sessionEvents(value: unknown): SessionEvent[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const event = item as Record<string, unknown>;
    if (typeof event.id !== "number" || typeof event.kind !== "string" || typeof event.title !== "string" || typeof event.evidence !== "string"
      || typeof event.started_at_seconds !== "number" || typeof event.duration_seconds !== "number"
      || typeof event.active !== "boolean") return [];
    return [{ id: event.id, kind: event.kind, title: event.title, evidence: event.evidence,
      startedAtSeconds: event.started_at_seconds, durationSeconds: event.duration_seconds, active: event.active }];
  });
}

function eventEvidence(event: SessionEvent) {
  const evidence = event.evidence.replace(/\bin (\d+(?:\.\d+)?)s\b/g, "within the last $1 seconds");
  // Repetition reports already describe a counting window, not a sustained hold.
  if (event.kind.startsWith("repeated_") || event.kind === "repetitive_hand_motion" || event.kind === "gaze_switching") return evidence;
  return `${evidence} · Duration: ${event.durationSeconds.toFixed(1)} seconds`;
}

function eventTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}


function coachingCategory(kind: string): "Eyes" | "Head" | "Body" | "Hands" | "Visibility" {
  if (kind === "object_obstruction") return "Visibility";
  if (["eye_away", "repeated_glances", "gaze_switching"].includes(kind)) return "Eyes";
  if (kind.includes("head")) return "Head";
  if (kind.startsWith("body_") || kind === "posture_drift") return "Body";
  return "Hands";
}

const eventCategoryColors = {
  Eyes: { box: "border-[#d6dff5] bg-[#f4f7ff]", badge: "bg-[#e6edff] text-[#4c68a0]" },
  Head: { box: "border-[#efc9bf] bg-[#fff1ec]", badge: "bg-[#fbdacf] text-[#a34d38]" },
  Body: { box: "border-[#cfe7df] bg-[#f2faf7]", badge: "bg-[#dff0e9] text-[#43836b]" },
  Hands: { box: "border-[#efddc5] bg-[#fff9f0]", badge: "bg-[#f8ead5] text-[#9b7039]" },
  Visibility: { box: "border-[#efd6dd] bg-[#fff5f8]", badge: "bg-[#f8e3ea] text-[#a36077]" },
};

function CoachingStatusIcon({ kind }: { kind: "eyes" | "head" | "body" | "hands" }) {
  return <svg aria-hidden="true" className="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
    {kind === "eyes" ? <><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" /></> : kind === "head" ? <path d="M9 21v-4H7a2 2 0 0 1-2-2v-3H3l2-4a7 7 0 1 1 13 5v8M9 8h.01" /> : kind === "body" ? <><circle cx="12" cy="4" r="2" /><path d="M8 21v-6H6l2-7h8l2 7h-2v6M12 15v6" /></> : <path d="M8 13V6a1.5 1.5 0 0 1 3 0v6-8a1.5 1.5 0 0 1 3 0v8-6a1.5 1.5 0 0 1 3 0v7-3a1.5 1.5 0 0 1 3 0v6a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-4-6a1.5 1.5 0 0 1 2.5-1.5L8 13Z" />}
  </svg>;
}

function liveStatusStyle(value: string, active: boolean, paused: boolean) {
  if (paused || ["Waiting", "Not assessed", "Calibrating"].includes(value)) return "border-[#e8e4ed] bg-[#f7f5f9] text-[#9a91a5]";
  if (active) return "border-[#efc5a1] bg-[#fff3e6] text-[#ad601c]";
  if (["Looking forward", "Facing forward", "Steady"].includes(value)) return "border-[#d6eade] bg-[#f1faf5] text-[#39815b]";
  return "border-[#eee0bc] bg-[#fffbef] text-[#9d792d]";
}


export default function LivePracticePage() {
  const { getAccessToken } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastFeedbackAtRef = useRef(0);
  const trackingStaleRef = useRef(false);
  const streamRef = useRef<MediaStream | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const poseLandmarkerRef = useRef<PoseLandmarker | null>(null);
  const handLandmarkerRef = useRef<HandLandmarker | null>(null);
  const objectDetectorRef = useRef<ObjectDetector | null>(null);
  const lastObjectSampleRef = useRef(0);
  const lastBodySampleRef = useRef(0);
  const lastVideoTimeRef = useRef(-1);
  const faceLandmarkerRef = useRef<FaceLandmarker | null>(null);
  const faceLandmarkerLoadingRef = useRef<Promise<FaceLandmarker> | null>(null);
  const sequenceRef = useRef(0);
  const analysingRef = useRef(false);
  const closingSocketRef = useRef(false);
  const endConfirmationOpenRef = useRef(false);
  const resumeAfterCancelRef = useRef(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [stage, setStage] = useState<Stage>("setup");
  const [permission, setPermission] = useState<Permission>("idle");
  const [connection, setConnection] = useState<ConnectionState>("idle");
  const [feedback, setFeedback] = useState<LiveFeedback | null>(null);
  const [targetFps, setTargetFps] = useState(15);
  const [sessionNote, setSessionNote] = useState("");
  const [sessionNoteTone, setSessionNoteTone] = useState<SessionNoteTone>("info");
  const [showDebug, setShowDebug] = useState(false);
  const debugVisible = debugAvailable && showDebug;

  const stopFrameCapture = () => {
    if (frameTimerRef.current !== null) window.clearInterval(frameTimerRef.current);
    frameTimerRef.current = null;
    analysingRef.current = false;
  };

  const stopStreaming = () => {
    stopFrameCapture();
    const socket = socketRef.current;
    socketRef.current = null;
    if (!socket) return;
    closingSocketRef.current = true;
    if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "end" }));
    socket.close();
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  const enableCamera = async () => {
    setSessionNote("");
    setSessionNoteTone("info");
    if (!navigator.mediaDevices?.getUserMedia) {
      setPermission("unavailable");
      return;
    }
    setPermission("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      stopCamera();
      streamRef.current = stream;
      stream.getVideoTracks().forEach((track) => {
        track.addEventListener("ended", () => {
          stopStreaming();
          streamRef.current = null;
          setStage("setup");
          setPermission("idle");
          setConnection("idle");
          setFeedback(null);
          setSessionNoteTone("error");
          setSessionNote("The camera disconnected. Reconnect it, then enable the camera again.");
        }, { once: true });
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setPermission("granted");
      setStage("calibrate");
    } catch {
      setPermission("denied");
    }
  };

  const requestEndSession = () => {
    if (endConfirmationOpenRef.current) return;
    endConfirmationOpenRef.current = true;
    resumeAfterCancelRef.current = stage === "live";
    // Stop sampling synchronously, before React opens the dialog or the server
    // acknowledges pause. No landmark detection runs behind the confirmation.
    stopFrameCapture();
    const socket = socketRef.current;
    if (stage === "live" && socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "pause" }));
    }
    setStage("paused");
    setConfirmEnd(true);
  };

  const cancelEndSession = () => {
    const shouldResume = resumeAfterCancelRef.current;
    endConfirmationOpenRef.current = false;
    resumeAfterCancelRef.current = false;
    setConfirmEnd(false);
    const socket = socketRef.current;
    if (shouldResume && socket?.readyState === WebSocket.OPEN && connection === "connected") {
      socket.send(JSON.stringify({ type: "resume" }));
      setStage("live");
    }
  };

  const endSession = () => {
    endConfirmationOpenRef.current = false;
    resumeAfterCancelRef.current = false;
    setConfirmEnd(false);
    stopStreaming();
    stopCamera();
    setStage("setup");
    setPermission("idle");
    setConnection("idle");
    setFeedback(null);
    setSessionNoteTone("info");
    setSessionNote("Live practice ended. No video was recorded or saved.");
  };

  const recalibrate = () => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    socket.send(JSON.stringify({ type: "recalibrate", timestamp_ms: Date.now() }));
  };

  const getFaceLandmarker = async () => {
    if (faceLandmarkerRef.current) return faceLandmarkerRef.current;
    if (!faceLandmarkerLoadingRef.current) {
      faceLandmarkerLoadingRef.current = (async () => {
        const { FaceLandmarker, PoseLandmarker, HandLandmarker, ObjectDetector, FilesetResolver } = await import("@mediapipe/tasks-vision");
        const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
        const landmarker = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            delegate: "CPU",
            modelAssetPath: "/mediapipe/face_landmarker.task",
          },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFacialTransformationMatrixes: true,
          minFaceDetectionConfidence: 0.5,
          minFacePresenceConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });
        try {
          poseLandmarkerRef.current = await PoseLandmarker.createFromOptions(vision, {
            baseOptions: { delegate: "CPU", modelAssetPath: "/mediapipe/pose_landmarker_lite.task" },
            runningMode: "VIDEO", numPoses: 1,
          });
          handLandmarkerRef.current = await HandLandmarker.createFromOptions(vision, {
            baseOptions: { delegate: "CPU", modelAssetPath: "/mediapipe/hand_landmarker.task" },
            runningMode: "VIDEO", numHands: 2,
          });
          objectDetectorRef.current = await ObjectDetector.createFromOptions(vision, {
            baseOptions: { delegate: "CPU", modelAssetPath: "/mediapipe/efficientdet_lite0.tflite" },
            runningMode: "VIDEO", scoreThreshold: .6, maxResults: 10,
          });
        } catch (error) {
          landmarker.close();
          poseLandmarkerRef.current?.close();
          poseLandmarkerRef.current = null;
          handLandmarkerRef.current?.close();
          handLandmarkerRef.current = null;
          throw error;
        }
        faceLandmarkerRef.current = landmarker;
        return landmarker;
      })().catch((error) => {
        faceLandmarkerLoadingRef.current = null;
        throw error;
      });
    }
    return faceLandmarkerLoadingRef.current;
  };

  const startCoaching = async () => {
    setSessionNote("");
    setSessionNoteTone("info");
    setConnection("connecting");
    setFeedback(null);
    closingSocketRef.current = false;
    try {
      setSessionNote("Loading the local eye tracker…");
      await getFaceLandmarker();
      const accessToken = await getAccessToken();
      if (!accessToken) throw new Error("Sign in before starting live coaching.");
      const socketUrl = `${apiBaseUrl.replace(/^http/, "ws")}/api/v1/live/stream`;
      const socket = new WebSocket(socketUrl);
      socketRef.current = socket;
      socket.onopen = () => socket.send(JSON.stringify({ type: "authenticate", access_token: accessToken }));
      socket.onmessage = (event) => {
        let message: unknown;
        try { message = JSON.parse(String(event.data)); } catch { return; }
        if (typeof message !== "object" || message === null || !("type" in message) || typeof message.type !== "string") return;
        if (message.type === "ready") {
          lastFeedbackAtRef.current = Date.now();
          trackingStaleRef.current = false;
          if ("target_fps" in message && typeof message.target_fps === "number") setTargetFps(Math.max(15, message.target_fps));
          setConnection("connected");
          setStage("live");
          setSessionNote("");
          return;
        }
        if (message.type === "feedback") {
          lastFeedbackAtRef.current = Date.now();
          trackingStaleRef.current = false;
          const status = "status" in message && message.status && typeof message.status === "object" ? message.status as Record<string, unknown> : {};
          const label = (key: string) => typeof status[key] === "string" ? status[key] as string : "Not assessed";
          setFeedback({
            status: { eyes: label("eyes"), head: label("head"), body: label("body"), hands: label("hands") },
            prompt: "message" in message && typeof message.message === "string" ? message.message : "Keep presenting naturally",
            personDetected: "person_detected" in message && message.person_detected === true,
            calibrationComplete: "calibration_complete" in message && message.calibration_complete === true,
            calibrationSamples: "calibration_samples" in message && typeof message.calibration_samples === "number" ? message.calibration_samples : 0,
            calibrationRequired: "calibration_required" in message && typeof message.calibration_required === "number" ? message.calibration_required : 15,
            debug: "debug" in message ? liveDebug(message.debug) : null,
            sessionEvents: "session_events" in message ? sessionEvents(message.session_events) : [],
          });
          return;
        }
        if (message.type === "recalibrating") {
          const calibrationRequired = "calibration_required" in message && typeof message.calibration_required === "number" ? message.calibration_required : 15;
          const prompt = "message" in message && typeof message.message === "string" ? message.message : "Look at the camera marker while eye contact is recalibrated.";
          setFeedback((current) => current ? {
            ...current,
            calibrationComplete: false,
            status: { eyes: "Calibrating", head: "Calibrating", body: "Calibrating", hands: "Not assessed" },
            calibrationSamples: 0,
            calibrationRequired,
            prompt,
          } : current);
          return;
        }
        if (message.type === "paused") {
          setStage("paused");
          setFeedback((current) => current ? {
            ...current,
            sessionEvents: "session_events" in message ? sessionEvents(message.session_events) : current.sessionEvents,
          } : current);
          return;
        }
        if (message.type === "resumed") {
          if (!endConfirmationOpenRef.current) setStage("live");
          return;
        }
        if (message.type === "error") {
          setConnection("error");
          setStage("calibrate");
          setSessionNoteTone("error");
          setSessionNote("message" in message && typeof message.message === "string" ? message.message : "Live coaching stopped.");
          return;
        }
        if (message.type === "warning") {
          setSessionNoteTone("warning");
          setSessionNote("message" in message && typeof message.message === "string" ? message.message : "A live observation was ignored.");
        }
      };
      socket.onerror = () => {
        setSessionNoteTone("error");
        setSessionNote("Coaching could not connect. Your camera is still on; try starting coaching again.");
      };
      socket.onclose = () => {
        if (!closingSocketRef.current) {
          setConnection("error");
          setStage((current) => current === "live" || current === "paused" ? "calibrate" : current);
          setSessionNoteTone("error");
          setSessionNote("Live coaching disconnected. You can try again.");
        }
      };
    } catch (error) {
      setConnection("error");
      setSessionNoteTone("error");
      setSessionNote(error instanceof Error ? error.message : "Live coaching could not start.");
    }
  };

  const sendObservation = () => {
    const socket = socketRef.current;
    const video = videoRef.current;
    const landmarker = faceLandmarkerRef.current;
    if (endConfirmationOpenRef.current || !video || !socket || !landmarker || socket.readyState !== WebSocket.OPEN || analysingRef.current || !video.videoWidth || !video.videoHeight) return;
    analysingRef.current = true;
    try {
      const timestamp = performance.now();
      if (video.currentTime === lastVideoTimeRef.current) return;
      lastVideoTimeRef.current = video.currentTime;
      const result = landmarker.detectForVideo(video, timestamp);
      // Face/iris updates run each frame; larger body/hand models run at 5 Hz.
      const updateBody = timestamp - lastBodySampleRef.current >= 200;
      let body, hands;
      if (updateBody) {
        lastBodySampleRef.current = timestamp;
        body = poseLandmarkerRef.current?.detectForVideo(video, timestamp).landmarks[0];
        hands = handLandmarkerRef.current?.detectForVideo(video, timestamp).landmarks;
      }
      const updateObjects = timestamp - lastObjectSampleRef.current >= 500;
      let objects;
      if (updateObjects) {
        lastObjectSampleRef.current = timestamp;
        const detections = objectDetectorRef.current?.detectForVideo(video, timestamp).detections ?? [];
        objects = objectsFromDetections(detections, video.videoWidth, video.videoHeight);
      }
      sequenceRef.current += 1;
      socket.send(JSON.stringify({ objects, objects_updated: updateObjects, type: "observation", sequence: sequenceRef.current, timestamp_ms: Date.now(),
        ...observationFromLandmarks(result.faceLandmarks[0], result.facialTransformationMatrixes[0], body, hands, updateBody, updateBody) }));
    } catch (error) {
      console.error("Live landmark processing failed", error);
      setSessionNoteTone("warning");
      setSessionNote("Movement tracking was interrupted. Pause and resume to try again.");
    } finally {
      analysingRef.current = false;
    }
  };

  useEffect(() => {
    if (stage !== "live" || connection !== "connected" || confirmEnd) return;
    sendObservation();
    frameTimerRef.current = window.setInterval(sendObservation, Math.round(1000 / targetFps));
    return stopFrameCapture;
  }, [connection, stage, targetFps, confirmEnd]);

  useEffect(() => {
    if (stage !== "live" || connection !== "connected" || confirmEnd) return;
    lastFeedbackAtRef.current = Date.now();
    trackingStaleRef.current = false;
    const timer = window.setInterval(() => {
      if (trackingStaleRef.current || Date.now() - lastFeedbackAtRef.current < 1500) return;
      trackingStaleRef.current = true;
      setFeedback((current) => current ? {
        ...current,
        status: { eyes: "Not assessed", head: "Not assessed", body: "Not assessed", hands: "Not assessed" },
        debug: null,
        prompt: "Waiting for camera tracking.",
        sessionEvents: current.sessionEvents.map((event) => ({ ...event, active: false })),
      } : current);
    }, 250);
    return () => window.clearInterval(timer);
  }, [connection, stage, confirmEnd]);

  useEffect(() => () => { stopStreaming(); stopCamera(); faceLandmarkerRef.current?.close(); poseLandmarkerRef.current?.close(); handLandmarkerRef.current?.close(); objectDetectorRef.current?.close(); }, []);

  useEffect(() => {
    if (stage === "live" || stage === "paused") return;
    endConfirmationOpenRef.current = false;
    resumeAfterCancelRef.current = false;
    setConfirmEnd(false);
  }, [stage]);

  useEffect(() => {
    if (!sessionNote || sessionNoteTone === "error") return;
    // Loading feedback remains until startup completes; confirmations expire.
    if (sessionNoteTone === "info" && stage !== "setup") return;
    const timer = window.setTimeout(() => setSessionNote(""), sessionNoteTone === "warning" ? 8000 : 4000);
    return () => window.clearTimeout(timer);
  }, [sessionNote, sessionNoteTone, stage]);

  const isSessionActive = stage === "live" || stage === "paused";
  const statusLabel = stage === "paused" ? "Paused" : stage === "live" ? "Live coaching" : stage === "calibrate" ? "Camera check" : "Ready";

  return (
    <main className={`min-h-dvh ${isSessionActive ? "lg:flex lg:h-dvh lg:min-h-0 lg:flex-col lg:overflow-hidden" : ""} bg-[#f7f7f9] text-[#1d1c2a] [background:radial-gradient(circle_at_85%_4%,#e4e0ff_0,transparent_28rem),radial-gradient(circle_at_7%_100%,#e8f6ff_0,transparent_32rem),#f7f7f9]`}>
      <header className="grid min-h-[74px] shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[#e7e6ed] bg-white/85 px-[clamp(1rem,3vw,3.25rem)] backdrop-blur">
        <Link className="w-fit rounded-lg no-underline" href="/home"><Brand /></Link>
        <div className="text-center">
          <h1 className="m-0 text-[1.2rem] font-extrabold tracking-[-0.055em] text-[#20202c]">Live Practice</h1>
          <p className="mb-0 mt-[0.1rem] text-[0.66rem] font-semibold text-[#81808d]">Practise your delivery with live coaching</p>
        </div>
        <div className="justify-self-end">
          <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[0.68rem] font-bold ${stage === "live" ? "border-[#ccebd8] bg-[#f4fff8] text-[#178f51]" : "border-[#e5e3ee] bg-white text-[#777583]"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${stage === "live" ? "bg-[#1db166] shadow-[0_0_0_3px_#dcf6e7]" : "bg-[#aaa7b7]"}`} />
            {statusLabel}
          </span>
        </div>
      </header>

      <section className={`mx-auto grid w-full max-w-[96rem] gap-5 px-[clamp(1rem,2.4vw,2.4rem)] py-[clamp(1rem,2vw,1.8rem)] ${isSessionActive ? "lg:min-h-0 lg:flex-1 lg:grid-rows-[minmax(0,1fr)]" : ""} lg:items-stretch lg:grid-cols-[minmax(0,65fr)_minmax(0,35fr)]`} aria-label="Live practice workspace">
        <section className="min-w-0">
          <div className="relative overflow-hidden rounded-[24px] border border-[#e1e0e8] bg-[#171724] shadow-[0_22px_60px_rgba(32,29,55,0.16)]">
            <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between p-4 sm:p-5">
              <span className="rounded-full border border-white/20 bg-[#171724]/55 px-3 py-1.5 text-[0.67rem] font-bold text-white backdrop-blur">{permission !== "granted" ? "Camera off" : stage === "live" ? "Live camera" : stage === "paused" ? "Camera on" : "Camera ready"}</span>
              {isSessionActive ? <span className="rounded-full bg-[#f0edff]/95 px-3 py-1.5 text-[0.67rem] font-bold text-[#5f4ee0]">{stage === "paused" ? "Paused" : connection === "connected" ? "Live feedback" : "Connecting…"}</span> : null}
            </div>

            <div className="relative aspect-[16/9] bg-[radial-gradient(circle_at_50%_42%,#545062_0,transparent_32%),linear-gradient(145deg,#242332,#15151d)]">
              <video autoPlay className={`absolute inset-0 h-full w-full -scale-x-100 object-cover transition-opacity duration-300 ${permission === "granted" ? "opacity-100" : "opacity-0"}`} muted playsInline ref={videoRef} />
              {permission !== "granted" ? <div className="absolute inset-0 grid place-items-center px-6 pb-6 pt-16 text-center"><div><span aria-hidden="true" className="mx-auto grid h-10 w-10 place-items-center rounded-xl border border-white/15 bg-white/5 text-[#bdb6d2]"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14 4h-4L8 7H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2-3Z" /><circle cx="12" cy="13" r="3" /></svg></span><h2 className="mb-0 mt-4 text-lg font-semibold tracking-tight text-white">{permission === "requesting" ? "Opening your camera…" : "Ready to practise?"}</h2><p className="mx-auto mb-0 mt-2 max-w-[300px] text-xs leading-5 text-[#aaa3bc]">Turn on your camera, get comfortable, then start coaching.</p></div></div> : null}

              {permission === "granted" ? <><div className="pointer-events-none absolute left-1/2 top-1/2 h-[74%] w-[48%] -translate-x-1/2 -translate-y-1/2 rounded-[24%] border border-white/80 shadow-[0_0_0_999px_rgba(20,19,31,0.12)]" /><div className="pointer-events-none absolute left-1/2 top-[14%] h-[6px] w-[6px] -translate-x-1/2 rounded-full bg-white shadow-[0_0_0_5px_rgba(255,255,255,0.16)]" />{debugVisible && feedback?.debug?.face ? <div className="pointer-events-none absolute z-10 border-2 border-[#68e6ff] shadow-[0_0_0_1px_rgba(12,40,52,0.5)]" style={{ left: `${(1 - feedback.debug.face.x - feedback.debug.face.width) * 100}%`, top: `${feedback.debug.face.y * 100}%`, width: `${feedback.debug.face.width * 100}%`, height: `${feedback.debug.face.height * 100}%` }} /> : null}{debugVisible && feedback?.debug?.leftEye ? <div className="pointer-events-none absolute z-10 border border-[#cf9bff]" style={{ left: `${(1 - feedback.debug.leftEye.x - feedback.debug.leftEye.width) * 100}%`, top: `${feedback.debug.leftEye.y * 100}%`, width: `${feedback.debug.leftEye.width * 100}%`, height: `${feedback.debug.leftEye.height * 100}%` }} /> : null}{debugVisible && feedback?.debug?.rightEye ? <div className="pointer-events-none absolute z-10 border border-[#cf9bff]" style={{ left: `${(1 - feedback.debug.rightEye.x - feedback.debug.rightEye.width) * 100}%`, top: `${feedback.debug.rightEye.y * 100}%`, width: `${feedback.debug.rightEye.width * 100}%`, height: `${feedback.debug.rightEye.height * 100}%` }} /> : null}{debugVisible && feedback?.debug ? <div className="pointer-events-none absolute right-4 top-16 z-10 rounded-lg border border-white/20 bg-[#171724]/75 px-2.5 py-2 font-mono text-[0.6rem] leading-5 text-[#effcff] backdrop-blur"><p className="m-0 text-[#68e6ff]">DEBUG · Face + iris landmarks</p><p className="m-0">gaze: {feedback.calibrationComplete ? feedback.status.eyes : `calibrating ${feedback.calibrationSamples}/${feedback.calibrationRequired}`}</p></div> : null}<p className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-[#171724]/60 px-3 py-1.5 text-center text-[0.66rem] font-medium text-white backdrop-blur">Use the outline as a framing guide and keep your eyes near the marker</p></> : null}
            </div>
          </div>

          <div className="mt-4 flex shrink-0 flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e4e3e9] bg-white px-4 py-3.5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]">
            <p className="m-0 max-w-[38rem] text-[0.74rem] leading-5 text-[#686675]">{stage === "live" ? "Coaching is running." : stage === "paused" ? "Tracking is paused. Resume when you’re ready." : permissionMessage(permission)}</p>
            <div className="flex flex-wrap items-center gap-2">
              {stage === "setup" ? <button className="inline-flex h-10 items-center justify-center leading-none rounded-lg bg-[#1d1c2a] px-3.5 py-0 text-[0.74rem] font-bold text-white disabled:cursor-wait disabled:opacity-60" disabled={permission === "requesting"} onClick={() => void enableCamera()} type="button">{permission === "requesting" ? "Opening camera…" : "Enable camera"}</button> : null}
              {stage === "calibrate" ? <><button className="inline-flex h-10 items-center justify-center leading-none rounded-lg border border-[#dedce5] bg-white px-3.5 py-0 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={endSession} type="button">Cancel</button><button className="inline-flex h-10 items-center justify-center gap-[5px] leading-none rounded-lg border border-[#6850db] bg-[#6850db] px-3.5 py-0 text-[0.74rem] font-bold text-white shadow-sm transition-colors hover:border-[#5941ca] hover:bg-[#5941ca] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4] disabled:cursor-wait disabled:opacity-60" disabled={connection === "connecting"} onClick={() => void startCoaching()} type="button"><SessionControlIcon action="play" />{connection === "connecting" ? "Connecting…" : "Start coaching"}</button></> : null}
              {stage === "live" ? <>{debugAvailable && <button className="inline-flex h-10 items-center justify-center leading-none rounded-lg border border-[#dedce5] bg-white px-3 py-0 text-[0.7rem] font-bold text-[#5d5b6a]" onClick={() => setShowDebug((visible) => !visible)} type="button">{showDebug ? "Hide tracking" : "Show tracking"}</button>}<div className="inline-flex items-center gap-1"><button className="inline-flex h-10 items-center justify-center leading-none rounded-lg border border-[#dedce5] bg-white px-3.5 py-0 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={recalibrate} type="button">Recalibrate</button><LiveRecalibrationHelp /></div><button className="inline-flex h-10 items-center justify-center gap-[5px] leading-none rounded-lg border border-[#e7d9b5] bg-[#fffbf0] px-3.5 py-0 text-[0.74rem] font-bold text-[#927021] transition-colors hover:border-[#d6bf84] hover:bg-[#fff4d8] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c49b43]" onClick={() => { socketRef.current?.send(JSON.stringify({ type: "pause" })); setStage("paused"); }} type="button"><SessionControlIcon action="pause" />Pause</button><button className="inline-flex h-10 items-center justify-center gap-[5px] leading-none rounded-lg border border-[#ebced4] bg-[#fff6f7] px-3.5 py-0 text-[0.74rem] font-bold text-[#b04b60] transition-colors hover:border-[#dca4b1] hover:bg-[#fce9ed] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c97084]" onClick={requestEndSession} type="button"><SessionControlIcon action="stop" />End session</button></> : null}
              {stage === "paused" ? <>
                {debugAvailable && <button className="inline-flex h-10 items-center justify-center leading-none rounded-lg border border-[#dedce5] bg-white px-3 py-0 text-[0.7rem] font-bold text-[#5d5b6a]" onClick={() => setShowDebug((visible) => !visible)} type="button">{showDebug ? "Hide tracking" : "Show tracking"}</button>}
                <button className="inline-flex h-10 items-center justify-center gap-[5px] leading-none rounded-lg border border-[#6850db] bg-[#6850db] px-3.5 py-0 text-[0.74rem] font-bold text-white shadow-sm transition-colors hover:border-[#5941ca] hover:bg-[#5941ca] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#8e7cf4] disabled:cursor-wait disabled:opacity-60" onClick={() => { socketRef.current?.send(JSON.stringify({ type: "resume" })); setStage("live"); }} type="button"><SessionControlIcon action="play" />Resume</button>
                <button className="inline-flex h-10 items-center justify-center gap-[5px] leading-none rounded-lg border border-[#ebced4] bg-[#fff6f7] px-3.5 py-0 text-[0.74rem] font-bold text-[#b04b60] transition-colors hover:border-[#dca4b1] hover:bg-[#fce9ed] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#c97084]" onClick={requestEndSession} type="button"><SessionControlIcon action="stop" />End session</button>
              </> : null}
            </div>
          </div>


        </section>

        <aside className={`min-w-0 ${isSessionActive ? "grid min-h-0 gap-4 lg:h-full lg:grid-rows-[auto_minmax(0,1fr)] lg:self-start" : "flex min-h-0 flex-col lg:[contain:size]"}`}>
          {!isSessionActive ? <><section className="shrink-0 rounded-2xl border border-[#e4e3e9] bg-white p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]"><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.1em] text-[#6755df]">{stage === "calibrate" ? "Calibration" : "Before you begin"}</p><h2 className="mb-0 mt-2 text-[1.18rem] tracking-[-0.05em]">{stage === "calibrate" ? "Check your camera position" : "Get ready to practise"}</h2><p className="mb-0 mt-3 text-[0.78rem] leading-6 text-[#676574]">{stage === "calibrate" ? "Face the camera with both eyes visible. When you’re comfortable, start coaching." : "Position your camera and turn it on. Coaching begins only when you choose Start coaching."}</p><ol className="mb-0 mt-5 grid list-none gap-3 p-0">{["Face a stable light source", "Keep both eyes visible", "Place the camera at eye level"].map((item, index) => <li className="grid grid-cols-[22px_1fr] items-start gap-2 text-[0.73rem] leading-5 text-[#4f4d5c]" key={item}><span className="grid h-[22px] w-[22px] place-items-center rounded-[7px] bg-[#f0edff] text-[0.62rem] font-extrabold text-[#6652e6]">0{index + 1}</span>{item}</li>)}</ol></section>
            <section className="mt-4 flex min-h-0 flex-1 flex-col rounded-2xl border border-[#e4e0ee] bg-white p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]" aria-labelledby="coaching-guide-title">
              <h2 id="coaching-guide-title" className="m-0 text-[0.95rem] font-semibold tracking-tight text-[#5c4a70]">What coaching looks for</h2>
              <p className="mb-0 mt-2 text-xs leading-5 text-[#93849f]">Coaching moments show what happened and when, so you can adjust as you speak.</p>
              <dl className="mb-0 mt-4 grid min-h-0 flex-1 auto-rows-[minmax(min-content,1fr)] divide-y divide-[#f0ecf5] overflow-y-auto">
                {[
                  ["Eyes", "Long look-aways or repeated glances."],
                  ["Head", "Repeated turns, nodding or shaking."],
                  ["Body", "Repeated swaying or a drifting posture."],
                  ["Hands", "Hands in view, face touching or blocking."],
                ].map(([label, description]) => <div key={label} className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-baseline gap-3 py-3"><dt className="flex items-center gap-2 text-xs font-semibold leading-5 text-[#877299]"><CoachingStatusIcon kind={label.toLowerCase() as "eyes" | "head" | "body" | "hands"} />{label}</dt><dd className="m-0 text-xs leading-5 text-[#93849f]">{description}</dd></div>)}
              </dl>
            </section>
          </> : <>
          <section className="min-h-0 overflow-y-auto rounded-2xl border border-[#e7e1ee] bg-white px-4 py-3" aria-label="Live coaching status">
            <div className="mb-3 flex items-center justify-between"><h2 className="m-0 text-sm font-semibold text-[#796788]">Live coaching</h2><span className="text-[0.6875rem] text-[#b0a1bd]">{stage === "paused" ? "Paused" : connection === "connected" ? "Current movements" : "Connecting…"}</span></div>
            <dl className="m-0 grid grid-cols-2 gap-2">{([['eyes', 'Eyes'], ['head', 'Head'], ['body', 'Body'], ['hands', 'Hands']] as const).map(([key, label]) => {
              const value = feedback?.status[key] ?? "Waiting";
              const active = Boolean(feedback?.sessionEvents.some((event) => event.active && coachingCategory(event.kind) === label));
              return <div key={key} className={`flex min-w-0 items-start justify-between gap-2 rounded-lg border px-3 py-2 ${liveStatusStyle(value, active, stage === "paused")}`}><dt className="text-[0.6875rem] opacity-75">{label}</dt><dd className="m-0 flex items-start gap-1.5 text-right text-xs font-semibold leading-4"><span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-current" />{value}</dd></div>;
            })}</dl>
          </section>
          <section className="flex min-h-[300px] lg:min-h-0 flex-col overflow-hidden rounded-2xl border border-[#ddd5f0] bg-white shadow-[0_12px_40px_-18px_rgba(59,36,102,0.16)]" aria-labelledby="coaching-moments-title">
            <header className="shrink-0 border-b border-[#eee9f5] bg-[#fcfaff] px-4 py-4">
              <div className="flex items-center justify-between gap-3">
                <h2 id="coaching-moments-title" className="m-0 text-base font-semibold leading-6 tracking-tight text-[#40324f]">Coaching moments</h2>
                <span className="shrink-0 text-xs font-medium leading-6 tabular-nums text-[#9989aa]">{feedback?.sessionEvents.length ?? 0} {(feedback?.sessionEvents.length ?? 0) === 1 ? "moment" : "moments"}</span>
              </div>
              <p className="mb-0 mt-1 text-xs leading-5 text-[#9989aa]">What to adjust as you practise</p>
            </header>
            {feedback?.sessionEvents.length ? <ol className="m-0 min-h-0 flex-1 list-none overflow-y-auto overscroll-contain px-2 py-1">{[...feedback.sessionEvents].reverse().map((event) => {
              const active = event.active && stage === "live";
              const category = coachingCategory(event.kind);
              const colors = eventCategoryColors[category];
              return <li className={`my-2 rounded-lg border px-3 py-2 ${colors.box} ${active ? "ring-1 ring-inset ring-[#d8b16e]" : ""}`} key={event.id}>
                <div className="mb-1 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2"><span className={`rounded-md px-1.5 py-0.5 text-[0.625rem] font-medium ${colors.badge}`}>{category}</span>{active && <span className="inline-flex items-center gap-1.5 text-[0.625rem] font-medium text-[#b47632]"><span className="h-1.5 w-1.5 rounded-full bg-[#d9a15b]" />Happening now</span>}</div>
                  <time className="shrink-0 rounded-md bg-[#f8f6fb] px-1.5 py-0.5 text-[0.6875rem] font-medium tabular-nums text-[#9e90ac]">{eventTime(event.startedAtSeconds)}</time>
                </div>
                <p className={`m-0 text-[0.8125rem] font-semibold leading-5 ${active ? "text-[#8d5d26]" : "text-[#4e3b5c]"}`}>{event.title}</p>
                <p className="mb-0 mt-0.5 text-[0.6875rem] leading-4 text-[#81718e]">{eventEvidence(event)}</p>
              </li>;
            })}</ol> : <div className="grid flex-1 place-items-center px-4 py-5 text-center"><div><span aria-hidden="true" className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-2xl border border-[#ece5f4] bg-[#faf7fe] text-[#b3a1c8]"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 6h12M8 12h12M8 18h8M3 6h.01M3 12h.01M3 18h.01" /></svg></span><h3 className="m-0 text-sm font-medium text-[#8d7a9e]">Your coaching moments will appear here</h3><p className="mx-auto mb-0 mt-2 max-w-[260px] text-xs leading-5 text-[#b0a0bd]">{stage === "paused" ? "Resume your session when you’re ready." : "Keep presenting. Sustained or repeated movements will be listed with a timestamp."}</p></div></div>}
            <footer className="shrink-0 border-t border-[#eee9f5] px-4 py-2 text-[0.6875rem] text-[#b0a0bc]">Only this session · Clears when you end practice</footer>
          </section></>}
        </aside>
        {!isSessionActive && <p className="m-0 -mt-2 px-1 text-[0.6875rem] leading-5 text-[#a99bb6] lg:col-span-2">No video is recorded or saved. Coaching moments stay only for this session.</p>}
      </section>
      {sessionNote ? <p role="status" className={`fixed bottom-4 left-1/2 z-40 m-0 flex items-start justify-between gap-3 w-[min(90vw,36rem)] -translate-x-1/2 rounded-xl border px-4 py-3 text-[0.73rem] font-medium shadow-lg ${sessionNoteTone === "error" ? "border-[#efc9d1] bg-[#fff6f8] text-[#a23f56]" : sessionNoteTone === "warning" ? "border-[#efd8b7] bg-[#fffaf1] text-[#9b641f]" : "border-[#d5eadf] bg-[#f5fff8] text-[#24724b]"}`}><span>{sessionNote}</span><button type="button" aria-label="Dismiss message" className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded hover:bg-black/5" onClick={() => setSessionNote("")}><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg></button></p> : null}
      {confirmEnd && isSessionActive && <EndLiveSessionDialog onCancel={cancelEndSession} onConfirm={endSession} />}
    </main>
  );
}
