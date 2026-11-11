"use client";
import { useEffect, useRef, useState } from "react";
import { gestureMarkers, gestureNeedsAdjustment, gestureTicks } from "@/lib/gesture-timeline";

type GestureCoaching = { assessment: "adjustment"; title: string; observation: string; impact: string; recommendation: string; evidence_seconds: number[] };
type Event = { type: string; label: string; start_seconds: number; end_seconds?: number; duration_seconds: number; feedback: string; evidence_image_url: string | null; evidence_video_url?: string | null; coaching?: GestureCoaching | null; detection?: { is_issue?: boolean } | null };
export type PoseTracking = {
  status: "reliable" | "limited" | "insufficient";
  reliable_body_percent: number;
  reliable_body_seconds: number;
  person_visible_percent: number;
  checks: { type: string; label: string; status: "reliable" | "limited" | "insufficient"; coverage_percent: number }[];
};
const time = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

// Filled upper-body pictograms keep the action readable at timeline size.
function GestureIcon({ type }: { type: string }) {
  const headMovement = type === "repeated_head_movement";
  const faceTouch = type === "hand_near_face";
  return <svg viewBox="0 0 48 48" width="32" height="32" fill="none" aria-hidden="true">
    {headMovement ? <>
      <path d="M12 44v-3c0-6 5-10 12-10s12 4 12 10v3" fill="currentColor" opacity=".25" />
      <rect x="16" y="10" width="16" height="19" rx="8" fill="currentColor" />
      <path d="M11 13H3m0 0 4-4m-4 4 4 4m30-4h8m0 0-4-4m4 4-4 4" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </> : faceTouch ? <>
      <path d="M9 44v-4c0-7 6-12 15-12s15 5 15 12v4" fill="currentColor" opacity=".25" />
      <rect x="17" y="5" width="16" height="20" rx="8" fill="currentColor" />
      <path d="m13 33-5-10 7-8" stroke="white" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="m13 33-5-10 7-8" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="m15 15 3-4m-3 4 5-1" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
    </> : <>
      <circle cx="24" cy="8" r="5" fill="currentColor" />
      <path d="M15 43V24a9 9 0 0 1 18 0v19Z" fill="currentColor" opacity=".25" />
      {type === "arms_crossed" ? <>
        <path d="m15 20-6 9 22 6 8-7-7-8" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <path d="m10 31 23-8" stroke="white" strokeWidth="8" strokeLinecap="round" />
        <path d="m10 31 23-8" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      </> : type === "gesture_box_excursion" ? <>
        <path d="M17 20 4 16m27 4 13-4" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
        <path d="M10 28H3m0 0 3-3m-3 3 3 3m32-3h7m0 0-3-3m3 3-3 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </> : type === "hands_clasped_low" ? <>
        <path d="m16 20-7 10 12 9m11-19 7 10-12 9" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
        <rect x="18" y="35" width="12" height="7" rx="3.5" fill="currentColor" stroke="white" strokeWidth="1.5" />
      </> : type === "repeated_swaying" ? <>
        <path d="m15 21-3 13m21-13 3 13" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />
        <path d="M8 12H2m0 0 3-3m-3 3 3 3m35-3h6m0 0-3-3m3 3-3 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M14 45c6-3 14-3 20 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </> : <path d="m16 20-6 13m22-13 6 13" stroke="currentColor" strokeWidth="4" strokeLinecap="round" />}
    </>}
  </svg>;
}

const gestureLabel = (event: Event) => event.label;
const gestureGroupLabels: Record<string, string> = {
  arms_crossed: "Arms across torso", gesture_box_excursion: "Wide sideways reach",
  hand_near_face: "Hands near face", hands_clasped_low: "Hands held together",
  repeated_swaying: "Body leaning & shifting", repeated_head_movement: "Head movement",
};
const momentKey = (event: Event) => `${event.type}:${event.start_seconds}:${event.duration_seconds}`;


function GestureReview({ event, token }: { event: Event; token: string | null }) {
  const [source, setSource] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const coaching = event.coaching;
  const path = event.evidence_video_url || event.evidence_image_url;
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl: string | null = null;
    setSource(null); setReady(false); setFailed(false);
    if (path && token) {
      void fetch((process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + path, {
        headers: { Authorization: `Bearer ${token}` }, signal: controller.signal,
      })
        .then(response => { if (!response.ok) throw new Error(); return response.blob(); })
        .then(blob => {
          if (controller.signal.aborted) return;
          objectUrl = URL.createObjectURL(blob);
          setSource(objectUrl);
        })
        .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    }
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [path, token]);
  const loading = Boolean(path && token && !ready && !failed);
  return <article className="practice-gesture-card">
    <div className="practice-gesture-evidence"><p className="practice-eyebrow">Replay the moment · {time(event.start_seconds)}</p>
    <div className="practice-gesture-media" aria-busy={loading}>
      {source && !failed && <div className={`practice-gesture-layer${!ready ? " practice-gesture-preload" : ""}`} aria-hidden={!ready}>
        {event.evidence_video_url
          ? <video src={source} controls={ready} playsInline preload="auto" onLoadedData={() => setReady(true)} onError={() => setFailed(true)} tabIndex={ready ? 0 : -1} aria-label={`Review gesture at ${time(event.start_seconds)}`} />
          : <img src={source} alt={`Detected ${event.label.toLowerCase()} at ${time(event.start_seconds)}`} onLoad={() => setReady(true)} onError={() => setFailed(true)} />}
      </div>}
      {loading && <div className="practice-gesture-loading" role="status"><span className="practice-gesture-spinner" aria-hidden="true" /><span className="sr-only">Loading replay…</span></div>}
      {(failed || !path || !token) && <p className="practice-gesture-load-status" role="status">{failed ? "The replay could not be loaded. Refresh to try again." : "The replay for this moment is unavailable."}</p>}
    </div>
      <p className="practice-gesture-caption">{event.evidence_video_url ? "Silent replay with the surrounding context." : "A captured moment from your recording."}</p>
    </div>
    <div className="practice-gesture-coaching" aria-live="polite"><p className="practice-gesture-selected-label" data-gesture={event.type}><GestureIcon type={event.type} />{gestureLabel(event)} <span>{time(event.start_seconds)}–{time(event.end_seconds ?? event.start_seconds + event.duration_seconds)}</span></p>
      {coaching && <><p className="practice-eyebrow">An adjustment to try</p><h3>{coaching.title}</h3>
      <div className="practice-gesture-explanation"><h4>What happened</h4><p>{coaching.observation}</p></div>
      <div className="practice-gesture-explanation"><h4>Why it matters</h4><p>{coaching.impact}</p></div>
      <div className="practice-gesture-action"><h4>Try this next</h4><p>{coaching.recommendation}</p></div></>}
    </div>
  </article>;
}

export function PracticeGestures({ events, token, tracking, duration = 0 }: { events: Event[]; token: string | null; tracking?: PoseTracking | null; duration?: number }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [selectionNotice, setSelectionNotice] = useState<{ key: string } | null>(null);
  useEffect(() => {
    if (!selectionNotice) return;
    const timer = window.setTimeout(() => setSelectionNotice(null), 2000);
    return () => window.clearTimeout(timer);
  }, [selectionNotice]);
  const ordered = events.filter(gestureNeedsAdjustment).sort((a, b) => a.start_seconds - b.start_seconds);
  const active = ordered.find(event => momentKey(event) === selected) ?? ordered[0];
  const groups = new Map<string, Event[]>();
  for (const event of ordered) groups.set(event.type, [...(groups.get(event.type) ?? []), event]);
  const end = Math.max(1, duration, ...events.map(event => event.end_seconds ?? event.start_seconds + event.duration_seconds));
  // Keep short and nearby detections individually clickable instead of drawing
  // markers on top of one another. Different behaviors retain separate rows.
  const timelineWidth = Math.max(560, end * 3);
  const axisPlot = useRef<HTMLDivElement | null>(null);
  const [plotWidth, setPlotWidth] = useState(timelineWidth);
  const hasIssues = Boolean(active);
  useEffect(() => {
    const element = axisPlot.current;
    if (!element) return;
    const measure = () => setPlotWidth(element.getBoundingClientRect().width);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasIssues]);
  const ticks = gestureTicks(end);
  return <section className="practice-panel"><div className="practice-panel-heading"><div><p className="practice-eyebrow">On camera</p><h2>Gestures & body language</h2><p className="practice-muted">See what happened, why it may matter, and one adjustment to try. Keep deliberate movements that support your message.</p></div></div>
    {tracking?.status !== "reliable" && <div className="practice-gesture-warning" role="status">
      <strong>{!tracking ? "Your saved moments are ready to watch" : tracking.status === "insufficient" ? "The speaker is difficult to see" : "Some parts of the recording are difficult to see"}</strong>
      <p>{!tracking ? "Choose a moment below to watch it and get feedback." : "For clearer feedback, keep your face, arms and torso in view with good lighting."}</p>
    </div>}
    {active ? <>
      <div className="practice-gesture-timeline-heading"><h3>Find a moment</h3><p className="practice-gesture-click-hint"><svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4v16m-6-6 6 6 6-6" /></svg>Click a gesture to see its replay and feedback below.</p></div>
      <div className="practice-gesture-timeline-scroll" role="region" aria-label="Gesture timeline, scroll horizontally for later moments" tabIndex={0}>
        <div className="practice-gesture-timeline" style={{ minWidth: timelineWidth + 228 }}>
          <div className="practice-gesture-axis"><span>Recording time</span><div ref={axisPlot}>{ticks.map(tick => <span key={tick.seconds} style={{ left: `${tick.leftPercent}%` }}>{time(tick.seconds)}</span>)}</div></div>
          {Array.from(groups, ([type, items]) => {
            // Percentages place bars on the same scale as the axis at every
            // viewport width. Measured pixels are used only for click/label lanes.
            const { markers, lanes } = gestureMarkers(items, end, plotWidth);
            return <div className="practice-gesture-track" data-gesture={type} key={type}>
              <div className="practice-gesture-track-label"><GestureIcon type={type} /><span>{gestureGroupLabels[type] ?? items[0].label}</span></div>
              <div className="practice-gesture-track-moments" style={{ height: lanes * 64 }}>
                {ticks.map(tick => <i aria-hidden="true" className="practice-gesture-grid-line" key={tick.seconds} style={{ left: `${tick.leftPercent}%` }} />)}
                {markers.map(({ item, leftPercent, widthPercent, hitWidth, lane }, index) => <div key={`${item.start_seconds}-${index}`} className={`practice-gesture-marker${item === active ? " is-selected" : ""}`} style={{ left: `${leftPercent}%`, width: `${widthPercent}%`, top: lane * 64 }}>
                  <span className="practice-gesture-duration" aria-hidden="true" />
                  <button type="button" style={{ width: hitWidth }} onClick={() => { setSelected(momentKey(item)); setSelectionNotice({ key: momentKey(item) }); }} aria-pressed={item === active} aria-label={`${gestureLabel(item)}, ${time(item.start_seconds)} to ${time(item.end_seconds ?? item.start_seconds + item.duration_seconds)}. Review evidence.`}>
                    <time>{time(item.start_seconds)}</time><span><GestureIcon type={type} /></span>
                  </button>
                  {selectionNotice?.key === momentKey(item) && <span role="status" className="practice-gesture-selection-notice" style={leftPercent > 75 ? { right: 8 } : { left: 44 }}>Replay updated below <span aria-hidden="true">↓</span></span>}
                </div>)}
              </div>
            </div>;
          })}
        </div>
      </div>
      <p className="practice-gesture-timeline-note">Selected moment · replay and coaching below</p>
      <GestureReview key={`${momentKey(active)}:${active.evidence_video_url || active.evidence_image_url}:${token}`} event={active} token={token} />
    </> : <p className="practice-empty">{tracking?.status === "reliable" ? "No gesture issues were identified in this recording." : "For clearer gesture feedback, record with your face, arms and torso in view."}</p>}
  </section>;
}
