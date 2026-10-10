"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FaceLandmarker } from "@mediapipe/tasks-vision";

import { useAuth } from "@/components/auth/auth-provider";
import { Brand } from "@/components/brand";
import { observationFromLandmarks, type DebugBounds } from "@/lib/live-observation";

type Stage = "setup" | "calibrate" | "live" | "paused";
type Permission = "idle" | "requesting" | "granted" | "denied" | "unavailable";
type ConnectionState = "idle" | "connecting" | "connected" | "error";
type SessionNoteTone = "info" | "warning" | "error";

type LiveDebug = {
  face: DebugBounds | null;
  leftEye: DebugBounds | null;
  rightEye: DebugBounds | null;
  gazeOffset: { x: number; y: number } | null;
  headYaw: number | null;
};

type SessionEvent = {
  kind: "fronting_balance" | "extended_look_away" | "head_yaw";
  startedAtSeconds: number;
  durationSeconds: number;
  active: boolean;
};

type LiveFeedback = {
  frontFacingRatio: number | null;
  frontFacing: boolean | null;
  gazeOnCamera: boolean | null;
  headYaw: "centered" | "slight" | "turned" | "unavailable";
  prompt: string;
  personDetected: boolean;
  thinkingAwaySeconds: number;
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
  const gazeOffset = candidate.gaze_offset;
  return {
    face: debugBounds(candidate.face),
    leftEye: debugBounds(candidate.left_eye),
    rightEye: debugBounds(candidate.right_eye),
    gazeOffset: gazeOffset && typeof gazeOffset === "object" && typeof (gazeOffset as Record<string, unknown>).x === "number" && typeof (gazeOffset as Record<string, unknown>).y === "number" ? { x: (gazeOffset as Record<string, number>).x, y: (gazeOffset as Record<string, number>).y } : null,
    headYaw: typeof candidate.head_yaw === "number" ? candidate.head_yaw : null,
  };
}

function permissionMessage(permission: Permission) {
  if (permission === "requesting") return "Requesting camera access…";
  if (permission === "denied") return "Camera access was blocked. Allow it in your browser settings, then try again.";
  if (permission === "unavailable") return "This browser does not support camera access.";
  if (permission === "granted") return "Camera preview is ready. Eye landmarks are analysed in this browser; no footage leaves your device.";
  return "Use your camera locally to check framing before you begin.";
}

function sessionEvents(value: unknown): SessionEvent[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const event = item as Record<string, unknown>;
    if (
      (event.kind !== "fronting_balance" && event.kind !== "extended_look_away" && event.kind !== "head_yaw")
      || typeof event.started_at_seconds !== "number"
      || typeof event.duration_seconds !== "number"
      || typeof event.active !== "boolean"
    ) return [];
    return [{
      kind: event.kind,
      startedAtSeconds: event.started_at_seconds,
      durationSeconds: event.duration_seconds,
      active: event.active,
    }];
  });
}

function eventLabel(event: SessionEvent) {
  if (event.kind === "fronting_balance") return "Facing balance needs attention";
  return event.kind === "extended_look_away" ? "Long gaze away" : "Head turned away";
}

function eventTime(seconds: number) {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainingSeconds}`;
}

function gazeStatus(feedback: LiveFeedback | null) {
  if (!feedback) return "Waiting";
  if (!feedback.calibrationComplete) return "Calibrating";
  if (feedback.gazeOnCamera === null) return "Eyes not detected";
  if (feedback.thinkingAwaySeconds >= 2) return `Away for ${feedback.thinkingAwaySeconds.toFixed(1)}s`;
  if (!feedback.gazeOnCamera) return "Brief glance away";
  return "Looking at camera";
}

function headDirection(status: LiveFeedback["headYaw"] | undefined) {
  if (status === "centered") return "Facing camera";
  if (status === "slight") return "Slight turn";
  if (status === "turned") return "Turned away";
  return status === "unavailable" ? "Not detected" : "Waiting";
}

export default function LivePracticePage() {
  const { getAccessToken } = useAuth();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const frameTimerRef = useRef<number | null>(null);
  const faceLandmarkerRef = useRef<FaceLandmarker | null>(null);
  const faceLandmarkerLoadingRef = useRef<Promise<FaceLandmarker> | null>(null);
  const sequenceRef = useRef(0);
  const analysingRef = useRef(false);
  const closingSocketRef = useRef(false);
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

  const endSession = () => {
    stopStreaming();
    stopCamera();
    setStage("setup");
    setPermission("idle");
    setConnection("idle");
    setFeedback(null);
    setSessionNoteTone("info");
    setSessionNote("Live practice ended. Eye landmarks stayed in your browser; no recording was stored.");
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
        const { FaceLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
        const vision = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
        const landmarker = await FaceLandmarker.createFromOptions(vision, {
          baseOptions: {
            delegate: "CPU",
            modelAssetPath: "/mediapipe/face_landmarker.task",
          },
          runningMode: "VIDEO",
          numFaces: 1,
          minFaceDetectionConfidence: 0.5,
          minFacePresenceConfidence: 0.5,
          minTrackingConfidence: 0.5,
        });
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
          if ("target_fps" in message && typeof message.target_fps === "number") setTargetFps(Math.max(15, message.target_fps));
          setConnection("connected");
          setStage("live");
          setSessionNote("");
          return;
        }
        if (message.type === "feedback") {
          const ratio = "front_facing_ratio" in message && typeof message.front_facing_ratio === "number" ? Math.round(message.front_facing_ratio * 100) : null;
          const yaw = "head_yaw" in message && (message.head_yaw === "centered" || message.head_yaw === "slight" || message.head_yaw === "turned" || message.head_yaw === "unavailable") ? message.head_yaw : "unavailable";
          const nextCue = "message" in message && typeof message.message === "string" ? message.message : "Live feedback is updating.";
          setFeedback({
            frontFacingRatio: ratio,
            frontFacing: "front_facing" in message && typeof message.front_facing === "boolean" ? message.front_facing : null,
            gazeOnCamera: "gaze_on_camera" in message && typeof message.gaze_on_camera === "boolean" ? message.gaze_on_camera : null,
            headYaw: yaw,
            prompt: nextCue,
            personDetected: "person_detected" in message && message.person_detected === true,
            thinkingAwaySeconds: "extended_look_away_seconds" in message && typeof message.extended_look_away_seconds === "number" ? message.extended_look_away_seconds : 0,
            calibrationComplete: "calibration_complete" in message && message.calibration_complete === true,
            calibrationSamples: "calibration_samples" in message && typeof message.calibration_samples === "number" ? message.calibration_samples : 0,
            calibrationRequired: "calibration_required" in message && typeof message.calibration_required === "number" ? message.calibration_required : 0,
            debug: "debug" in message ? liveDebug(message.debug) : null,
            sessionEvents: "session_events" in message ? sessionEvents(message.session_events) : [],
          });
          return;
        }
        if (message.type === "recalibrating") {
          const calibrationRequired = "calibration_required" in message && typeof message.calibration_required === "number" ? message.calibration_required : 6;
          const prompt = "message" in message && typeof message.message === "string" ? message.message : "Look at the camera marker while eye contact is recalibrated.";
          setFeedback((current) => current ? {
            ...current,
            calibrationComplete: false,
            calibrationSamples: 0,
            calibrationRequired,
            gazeOnCamera: null,
            thinkingAwaySeconds: 0,
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
          setStage("live");
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
        setSessionNote("Live coaching could not connect. Your camera preview remains local.");
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
    if (!video || !socket || !landmarker || socket.readyState !== WebSocket.OPEN || analysingRef.current || !video.videoWidth || !video.videoHeight) return;
    analysingRef.current = true;
    try {
      const timestamp = performance.now();
      const result = landmarker.detectForVideo(video, timestamp);
      sequenceRef.current += 1;
      socket.send(JSON.stringify({ type: "observation", sequence: sequenceRef.current, timestamp_ms: Date.now(), ...observationFromLandmarks(result.faceLandmarks[0]) }));
    } catch {
      setSessionNoteTone("warning");
      setSessionNote("Eye tracking could not read this camera frame. Keep your face and eyes in view.");
    } finally {
      analysingRef.current = false;
    }
  };

  useEffect(() => {
    if (stage !== "live" || connection !== "connected") return;
    sendObservation();
    frameTimerRef.current = window.setInterval(sendObservation, Math.round(1000 / targetFps));
    return stopFrameCapture;
  }, [connection, stage, targetFps]);

  useEffect(() => () => { stopStreaming(); stopCamera(); faceLandmarkerRef.current?.close(); }, []);

  const isSessionActive = stage === "live" || stage === "paused";
  const statusLabel = stage === "paused" ? "Paused" : stage === "live" ? "Live coaching" : stage === "calibrate" ? "Camera check" : "Ready";

  return (
    <main className="min-h-dvh bg-[#f7f7f9] text-[#1d1c2a] [background:radial-gradient(circle_at_85%_4%,#e4e0ff_0,transparent_28rem),radial-gradient(circle_at_7%_100%,#e8f6ff_0,transparent_32rem),#f7f7f9]">
      <header className="grid min-h-[74px] grid-cols-[1fr_auto_1fr] items-center border-b border-[#e7e6ed] bg-white/85 px-[clamp(1rem,3vw,3.25rem)] backdrop-blur">
        <Link className="w-fit rounded-lg no-underline" href="/home"><Brand /></Link>
        <div className="text-center">
          <h1 className="m-0 text-[1.2rem] font-extrabold tracking-[-0.055em] text-[#20202c]">Live Practice</h1>
          <p className="mb-0 mt-[0.1rem] text-[0.66rem] font-semibold text-[#81808d]">Local camera preview · delivery coaching</p>
        </div>
        <div className="justify-self-end">
          <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[0.68rem] font-bold ${stage === "live" ? "border-[#ccebd8] bg-[#f4fff8] text-[#178f51]" : "border-[#e5e3ee] bg-white text-[#777583]"}`}>
            <span className={`h-1.5 w-1.5 rounded-full ${stage === "live" ? "bg-[#1db166] shadow-[0_0_0_3px_#dcf6e7]" : "bg-[#aaa7b7]"}`} />
            {statusLabel}
          </span>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-[96rem] gap-5 px-[clamp(1rem,2.4vw,2.4rem)] py-[clamp(1rem,2vw,1.8rem)] lg:grid-cols-[minmax(0,1fr)_20rem]" aria-label="Live practice workspace">
        <section className="min-w-0">
          <div className="relative overflow-hidden rounded-[24px] border border-[#e1e0e8] bg-[#171724] shadow-[0_22px_60px_rgba(32,29,55,0.16)]">
            <div className="absolute inset-x-0 top-0 z-10 flex items-center justify-between p-4 sm:p-5">
              <span className="rounded-full border border-white/20 bg-[#171724]/55 px-3 py-1.5 text-[0.67rem] font-bold text-white backdrop-blur">{stage === "setup" ? "Camera is off" : "Camera preview"}</span>
              {isSessionActive ? <span className="rounded-full bg-[#f0edff]/95 px-3 py-1.5 text-[0.67rem] font-bold text-[#5f4ee0]">{connection === "connected" ? "Live feedback" : "Connecting…"}</span> : null}
            </div>

            <div className="relative aspect-[16/9] min-h-[23rem] bg-[radial-gradient(circle_at_50%_42%,#545062_0,transparent_32%),linear-gradient(145deg,#242332,#15151d)]">
              <video autoPlay className={`h-full w-full object-cover transition-opacity duration-300 ${permission === "granted" ? "opacity-100" : "opacity-0"}`} muted playsInline ref={videoRef} />
              {permission !== "granted" ? <div className="absolute inset-0 grid place-items-center p-8 text-center"><div><span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-white/15 bg-white/10 text-[1.4rem] text-white">◉</span><h2 className="mb-0 mt-5 text-[1.25rem] font-extrabold tracking-[-0.045em] text-white">Camera preview stays on your device</h2><p className="mx-auto mb-0 mt-2 max-w-[28rem] text-[0.8rem] leading-6 text-[#cbc8d9]">Enable your camera to check your framing. The preview does not record, upload, or store footage.</p></div></div> : null}

              {permission === "granted" ? <><div className="pointer-events-none absolute left-1/2 top-1/2 h-[74%] w-[48%] -translate-x-1/2 -translate-y-1/2 rounded-[24%] border border-white/80 shadow-[0_0_0_999px_rgba(20,19,31,0.12)]" /><div className="pointer-events-none absolute left-1/2 top-[14%] h-[6px] w-[6px] -translate-x-1/2 rounded-full bg-white shadow-[0_0_0_5px_rgba(255,255,255,0.16)]" />{debugVisible && feedback?.debug?.face ? <div className="pointer-events-none absolute z-10 border-2 border-[#68e6ff] shadow-[0_0_0_1px_rgba(12,40,52,0.5)]" style={{ left: `${feedback.debug.face.x * 100}%`, top: `${feedback.debug.face.y * 100}%`, width: `${feedback.debug.face.width * 100}%`, height: `${feedback.debug.face.height * 100}%` }} /> : null}{debugVisible && feedback?.debug?.leftEye ? <div className="pointer-events-none absolute z-10 border border-[#cf9bff]" style={{ left: `${feedback.debug.leftEye.x * 100}%`, top: `${feedback.debug.leftEye.y * 100}%`, width: `${feedback.debug.leftEye.width * 100}%`, height: `${feedback.debug.leftEye.height * 100}%` }} /> : null}{debugVisible && feedback?.debug?.rightEye ? <div className="pointer-events-none absolute z-10 border border-[#cf9bff]" style={{ left: `${feedback.debug.rightEye.x * 100}%`, top: `${feedback.debug.rightEye.y * 100}%`, width: `${feedback.debug.rightEye.width * 100}%`, height: `${feedback.debug.rightEye.height * 100}%` }} /> : null}{debugVisible && feedback?.debug ? <div className="pointer-events-none absolute right-4 top-16 z-10 rounded-lg border border-white/20 bg-[#171724]/75 px-2.5 py-2 font-mono text-[0.6rem] leading-5 text-[#effcff] backdrop-blur"><p className="m-0 text-[#68e6ff]">DEBUG · Face + iris landmarks</p><p className="m-0">gaze: {feedback.calibrationComplete ? feedback.gazeOnCamera ? "on camera" : "away" : `calibrating ${feedback.calibrationSamples}/${feedback.calibrationRequired}`}</p>{feedback.debug.gazeOffset ? <p className="m-0">iris Δ: {feedback.debug.gazeOffset.x.toFixed(2)}, {feedback.debug.gazeOffset.y.toFixed(2)}</p> : null}{feedback.debug.headYaw !== null ? <p className="m-0">yaw: {feedback.debug.headYaw.toFixed(2)}</p> : null}</div> : null}<p className="pointer-events-none absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-[#171724]/60 px-3 py-1.5 text-center text-[0.66rem] font-medium text-white backdrop-blur">Use the outline as a framing guide and keep your eyes near the marker</p></> : null}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[#e4e3e9] bg-white px-4 py-3.5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]">
            <p className="m-0 max-w-[38rem] text-[0.74rem] leading-5 text-[#686675]">{permissionMessage(permission)}</p>
            <div className="flex shrink-0 gap-2">
              {stage === "setup" ? <button className="rounded-lg bg-[#1d1c2a] px-4 py-2.5 text-[0.74rem] font-bold text-white disabled:cursor-wait disabled:opacity-60" disabled={permission === "requesting"} onClick={() => void enableCamera()} type="button">{permission === "requesting" ? "Opening camera…" : "Enable camera"}</button> : null}
              {stage === "calibrate" ? <><button className="rounded-lg border border-[#dedce5] bg-white px-4 py-2.5 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={endSession} type="button">Cancel</button><button className="rounded-lg bg-[#1d1c2a] px-4 py-2.5 text-[0.74rem] font-bold text-white disabled:cursor-wait disabled:opacity-60" disabled={connection === "connecting"} onClick={() => void startCoaching()} type="button">{connection === "connecting" ? "Connecting…" : "Start coaching"}</button></> : null}
              {stage === "live" ? <>{debugAvailable && <button className="rounded-lg border border-[#dedce5] bg-white px-3 py-2.5 text-[0.7rem] font-bold text-[#5d5b6a]" onClick={() => setShowDebug((visible) => !visible)} type="button">{showDebug ? "Hide tracking" : "Show tracking"}</button>}<div className="inline-flex items-center gap-1"><button className="rounded-lg border border-[#dedce5] bg-white px-4 py-2.5 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={recalibrate} type="button">Recalibrate</button><span aria-label="Reset eye tracking after moving your camera, chair, or screen. Your current session history is kept." className="grid h-5 w-5 cursor-help place-items-center rounded-full border border-[#d8d5e4] text-[0.63rem] font-extrabold text-[#716d7d]" title="Reset eye tracking after moving your camera, chair, or screen. Your current session history is kept.">?</span></div><button className="rounded-lg border border-[#dedce5] bg-white px-4 py-2.5 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={() => { socketRef.current?.send(JSON.stringify({ type: "pause" })); setStage("paused"); }} type="button">Ⅱ Pause</button><button className="rounded-lg bg-[#1d1c2a] px-4 py-2.5 text-[0.74rem] font-bold text-white" onClick={endSession} type="button">End session</button></> : null}
              {stage === "paused" ? <>{debugAvailable && <button className="rounded-lg border border-[#dedce5] bg-white px-3 py-2.5 text-[0.7rem] font-bold text-[#5d5b6a]" onClick={() => setShowDebug((visible) => !visible)} type="button">{showDebug ? "Hide tracking" : "Show tracking"}</button>}<button className="rounded-lg border border-[#dedce5] bg-white px-4 py-2.5 text-[0.74rem] font-bold text-[#5d5b6a]" onClick={endSession} type="button">End session</button><button className="rounded-lg bg-[#1d1c2a] px-4 py-2.5 text-[0.74rem] font-bold text-white" onClick={() => { socketRef.current?.send(JSON.stringify({ type: "resume" })); setStage("live"); }} type="button">Resume</button></> : null}
            </div>
          </div>
          {sessionNote ? <p className={`mb-0 mt-3 rounded-xl border px-4 py-3 text-[0.73rem] font-medium ${sessionNoteTone === "error" ? "border-[#efc9d1] bg-[#fff6f8] text-[#a23f56]" : sessionNoteTone === "warning" ? "border-[#efd8b7] bg-[#fffaf1] text-[#9b641f]" : "border-[#d5eadf] bg-[#f5fff8] text-[#24724b]"}`}>{sessionNote}</p> : null}
        </section>

        <aside className="grid content-start gap-4">
          {!isSessionActive ? <section className="rounded-2xl border border-[#e4e3e9] bg-white p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]"><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.1em] text-[#6755df]">{stage === "calibrate" ? "Calibration" : "Before you begin"}</p><h2 className="mb-0 mt-2 text-[1.18rem] tracking-[-0.05em]">{stage === "calibrate" ? "Frame yourself comfortably" : "Practice with clarity"}</h2><p className="mb-0 mt-3 text-[0.78rem] leading-6 text-[#676574]">{stage === "calibrate" ? "Use the outline as a visual comfort guide—not a measured score. Keep your face and both eyes visible, with a little space above your head." : "Start with a local camera check. Live coaching measures observable delivery signals, not personality or emotion."}</p><ol className="mb-0 mt-5 grid list-none gap-3 p-0">{["Face a stable light source", "Keep both eyes visible", "Place the camera at eye level"].map((item, index) => <li className="grid grid-cols-[22px_1fr] items-start gap-2 text-[0.73rem] leading-5 text-[#4f4d5c]" key={item}><span className="grid h-[22px] w-[22px] place-items-center rounded-[7px] bg-[#f0edff] text-[0.62rem] font-extrabold text-[#6652e6]">0{index + 1}</span>{item}</li>)}</ol></section> : <><section className={`rounded-2xl border p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)] ${stage === "paused" ? "border-[#e5e3eb] bg-white" : "border-[#dad4ff] bg-[#faf9ff]"}`}><div className="flex items-start justify-between gap-3"><div><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.1em] text-[#6755df]">Current coaching cue</p><h2 className="mb-0 mt-2 text-[1.08rem] leading-[1.15] tracking-[-0.045em]">{stage === "paused" ? "Session paused" : feedback?.prompt ?? "Waiting for the first frame"}</h2></div><span className={`grid h-9 w-9 place-items-center rounded-xl text-[1rem] ${stage === "paused" ? "bg-[#f0eff3] text-[#85818f]" : "bg-[#e9e4ff] text-[#6652e6]"}`}>{stage === "paused" ? "Ⅱ" : "✦"}</span></div><p className="mb-0 mt-3 text-[0.77rem] leading-6 text-[#686574]">{stage === "paused" ? "Temporary observations are paused. Resume whenever you are ready." : feedback?.personDetected === false ? "Keep your face and eyes within the guide." : "Only numerical movement signals are sent for this session; video stays on your device."}</p></section><section className="rounded-2xl border border-[#e4e3e9] bg-white p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]"><div className="flex items-center justify-between"><h2 className="m-0 text-[0.86rem] tracking-[-0.025em]">Live indicators</h2><span className={`rounded-full px-2 py-1 text-[0.59rem] font-bold ${connection === "connected" ? "bg-[#e8f9ef] text-[#198b50]" : "bg-[#fff2dc] text-[#a86612]"}`}>{connection === "connected" ? "Live" : "Connecting"}</span></div><dl className="mb-0 mt-4 grid gap-0 divide-y divide-[#edecf1]"><div className="flex items-center justify-between py-3"><dt className="text-[0.72rem] font-semibold text-[#777483]">Facing the camera</dt><dd className="m-0 text-[1.05rem] font-extrabold tracking-[-0.05em] text-[#5e4ce0]">{feedback?.frontFacingRatio === null || feedback?.frontFacingRatio === undefined ? "Waiting" : `${feedback.frontFacingRatio}%`}</dd></div><div className="flex items-center justify-between gap-4 py-3"><dt className="text-[0.72rem] font-semibold text-[#777483]">Eye direction</dt><dd className={`m-0 text-right text-[0.75rem] font-extrabold ${feedback?.gazeOnCamera === false ? "text-[#b56a12]" : "text-[#1b9959]"}`}>{gazeStatus(feedback)}</dd></div><div className="flex items-center justify-between py-3"><dt className="text-[0.72rem] font-semibold text-[#777483]">Head direction</dt><dd className={`m-0 text-right text-[0.75rem] font-extrabold ${feedback?.headYaw === "centered" ? "text-[#1b9959]" : "text-[#a86612]"}`}>{headDirection(feedback?.headYaw)}</dd></div></dl></section></>}
          {isSessionActive ? <section className="overflow-hidden rounded-2xl border border-[#e4e3e9] bg-white shadow-[0_8px_24px_rgba(39,36,63,0.035)]"><div className="flex items-center justify-between border-b border-[#edecf1] px-5 py-4"><div><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.1em] text-[#6755df]">Session events</p><h2 className="mb-0 mt-1 text-[0.92rem] tracking-[-0.03em]">Coaching moments</h2></div><span className="rounded-full bg-[#f0edff] px-2 py-1 text-[0.61rem] font-bold text-[#6452df]">{feedback?.sessionEvents.length ?? 0}</span></div>{feedback?.sessionEvents.length ? <ol className="m-0 grid max-h-56 list-none gap-0 overflow-y-auto p-0">{[...feedback.sessionEvents].reverse().map((event, index) => <li className="grid grid-cols-[9px_minmax(0,1fr)] gap-3 border-b border-[#f0eff3] px-5 py-3 last:border-b-0" key={`${event.kind}-${event.startedAtSeconds}-${index}`}><span className={`mt-1.5 h-2 w-2 rounded-full ${event.active ? "bg-[#f39a31] shadow-[0_0_0_4px_#fff0dc]" : "bg-[#a6a2b2]"}`} /><div className="min-w-0"><div className="flex items-baseline justify-between gap-3"><p className="m-0 text-[0.73rem] font-bold text-[#413f4f]">{eventLabel(event)}</p><time className="shrink-0 text-[0.63rem] font-semibold text-[#9692a1]">{eventTime(event.startedAtSeconds)}</time></div><p className="mb-0 mt-1 text-[0.67rem] text-[#777482]">{event.active ? `${event.durationSeconds.toFixed(1)}s · happening now` : `${event.durationSeconds.toFixed(1)}s`}</p></div></li>)}</ol> : <p className="mb-0 px-5 py-4 text-[0.72rem] leading-5 text-[#777482]">No coaching moments yet. Facing-balance, sustained-gaze, and head-yaw events will appear here.</p>}</section> : null}
          <section className="rounded-2xl border border-[#e4e3e9] bg-white p-5 shadow-[0_8px_24px_rgba(39,36,63,0.035)]"><p className="m-0 text-[0.67rem] font-bold uppercase tracking-[0.1em] text-[#858292]">Privacy</p><p className="mb-0 mt-2 text-[0.74rem] leading-5 text-[#676574]">Your camera stays private. Rehearse AI only uses live movement signals to guide you during this practice—no video is recorded or saved.</p></section>
        </aside>
      </section>
    </main>
  );
}
