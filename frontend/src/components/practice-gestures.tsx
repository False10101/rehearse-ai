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

// Each icon depicts the observed movement, not an inferred emotion or intention.
function GestureIcon({ type }: { type: string }) {
  return <svg viewBox="0 0 32 32" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="16" cy="7" r="3" /><path d="M12 13h8l2 12H10zM12 25l-1 5m9-5 1 5" />
    {type === "arms_crossed" ? <path d="m9 14 12 7 3-7M23 14l-12 7-3-7" />
      : type === "gesture_box_excursion" ? <path d="M12 14 2 12m18 2 10-2M2 12l3-2m25 2-3-2" />
      : type === "hand_near_face" ? <path d="m12 14-5 6-2-10 6-1M20 14l5 9" />
      : type === "hands_clasped_low" ? <><path d="m10 14-3 7 8 3m7-10 3 7-8 3" /><circle cx="16" cy="24" r="2" /></>
      : type === "repeated_swaying" ? <path d="M6 15H1m0 0 2-2m-2 2 2 2m23-2h5m0 0-2-2m2 2-2 2" />
      : type === "repeated_head_movement" ? <path d="M10 4H3m0 0 2-2M3 4l2 2m17-2h7m0 0-2-2m2 2-2 2" />
      : <path d="m12 14-6 8m14-8 6 8" />}
  </svg>;
}

const gestureLabel = (event: Event) => event.type === "gesture_box_excursion" ? "Wide sideways reach" : event.label;
const momentKey = (event: Event) => `${event.type}:${event.start_seconds}:${event.duration_seconds}`;


function GestureReview({ event, token }: { event: Event; token: string | null }) {
  type Replay = { url: string; video: boolean; timestamp: number; label: string };
  const [replay, setReplay] = useState<Replay | null>(null);
  const [incoming, setIncoming] = useState<Replay | null>(null);
  const [loading, setLoading] = useState(false);
  const urls = useRef(new Map<string, string>());
  const player = useRef<HTMLVideoElement | null>(null);
  const [failed, setFailed] = useState(false);
  const coaching = event.coaching;
  const path = event.evidence_video_url || event.evidence_image_url;
  useEffect(() => {
    const cache = urls.current;
    return () => { for (const url of cache.values()) URL.revokeObjectURL(url); cache.clear(); };
  }, [token]);
  useEffect(() => {
    setIncoming(null); setFailed(false);
    player.current?.pause();
    if (!path || !token) { setReplay(null); setLoading(false); return; }
    setLoading(true);
    const controller = new AbortController();
    const next = (url: string) => setIncoming({ url, video: Boolean(event.evidence_video_url), timestamp: event.start_seconds, label: event.label });
    const cached = urls.current.get(path);
    if (cached) { next(cached); return; }
    void fetch((process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000") + path, { headers: { Authorization: `Bearer ${token}` }, signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.blob(); })
      .then(blob => { if (!controller.signal.aborted) { const url = URL.createObjectURL(blob); urls.current.set(path, url); next(url); } })
      .catch(() => { if (!controller.signal.aborted) { setFailed(true); setLoading(false); } });
    return () => controller.abort();
  }, [path, token, event.evidence_video_url, event.start_seconds, event.label]);
  const ready = () => { if (incoming) { setReplay(incoming); setIncoming(null); setLoading(false); } };
  const mediaFailed = () => { setIncoming(null); setLoading(false); setFailed(true); };
  return <article className="practice-gesture-card">
    <div className="practice-gesture-evidence"><p className="practice-eyebrow">Replay the moment · {time(event.start_seconds)}</p>
    <div className="practice-gesture-media" aria-busy={loading}>{[replay, incoming].filter((item): item is Replay => item !== null).map((item, index) => {
      const pending = index === (replay ? 1 : 0) && incoming !== null;
      return <div key={`${item.url}-${pending && replay?.url === item.url ? "reload" : "media"}`} className={`practice-gesture-layer${pending ? " practice-gesture-preload" : ""}`} aria-hidden={pending}>{item.video
        ? <video ref={pending ? undefined : player} src={item.url} controls={!pending && !loading && !failed} playsInline preload="auto" onLoadedData={pending ? ready : undefined} onError={pending ? mediaFailed : undefined} tabIndex={pending ? -1 : 0} aria-label={`Review gesture at ${time(item.timestamp)}`} />
        : <img src={item.url} alt={pending ? "" : `Detected ${item.label.toLowerCase()} at ${time(item.timestamp)}`} onLoad={pending ? ready : undefined} onError={pending ? mediaFailed : undefined} />}</div>;
    })}
      {(loading || failed || !path) && <p className="practice-gesture-load-status" role="status">{failed ? "The replay could not be loaded. Refresh to try again." : path ? "Loading replay…" : "The replay for this moment is unavailable."}</p>}
    </div>
      <p className="practice-gesture-caption">{event.evidence_video_url ? "Silent replay with the surrounding context." : "A captured moment from your recording."}</p>
    </div>
    <div className="practice-gesture-coaching" aria-live="polite"><p className="practice-gesture-selected-label"><GestureIcon type={event.type} />{gestureLabel(event)} <span>{time(event.start_seconds)}–{time(event.end_seconds ?? event.start_seconds + event.duration_seconds)}</span></p>
      {coaching && <><p className="practice-eyebrow">An adjustment to try</p><h3>{coaching.title}</h3>
      <div className="practice-gesture-explanation"><h4>What happened</h4><p>{coaching.observation}</p></div>
      <div className="practice-gesture-explanation"><h4>Why it matters</h4><p>{coaching.impact}</p></div>
      <div className="practice-gesture-action"><h4>Try this next</h4><p>{coaching.recommendation}</p></div></>}
    </div>
  </article>;
}

export function PracticeGestures({ events, token, tracking, duration = 0 }: { events: Event[]; token: string | null; tracking?: PoseTracking | null; duration?: number }) {
  const [selected, setSelected] = useState<string | null>(null);
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
      <div className="practice-gesture-timeline-heading"><h3>Gestures to improve</h3><p>Choose an icon to see the replay and an adjustment to try. Different rows can happen at the same time.</p></div>
      <div className="practice-gesture-timeline-scroll" role="region" aria-label="Gesture timeline, scroll horizontally for later moments" tabIndex={0}>
        <div className="practice-gesture-timeline" style={{ minWidth: timelineWidth + 228 }}>
          <div className="practice-gesture-axis"><span>Recording time</span><div ref={axisPlot}>{ticks.map(tick => <span key={tick.seconds} style={{ left: `${tick.leftPercent}%` }}>{time(tick.seconds)}</span>)}</div></div>
          {Array.from(groups, ([type, items]) => {
            // Percentages place bars on the same scale as the axis at every
            // viewport width. Measured pixels are used only for click/label lanes.
            const { markers, lanes } = gestureMarkers(items, end, plotWidth);
            return <div className="practice-gesture-track" key={type}>
              <div className="practice-gesture-track-label"><GestureIcon type={type} /><span>{gestureLabel(items[0])}</span></div>
              <div className="practice-gesture-track-moments" style={{ height: lanes * 78 }}>
                {ticks.map(tick => <i aria-hidden="true" className="practice-gesture-grid-line" key={tick.seconds} style={{ left: `${tick.leftPercent}%` }} />)}
                {markers.map(({ item, leftPercent, widthPercent, hitWidth, lane }, index) => <div key={`${item.start_seconds}-${index}`} className={`practice-gesture-marker${item === active ? " is-selected" : ""}`} style={{ left: `${leftPercent}%`, width: `${widthPercent}%`, top: lane * 78 }}>
                  <span className="practice-gesture-duration" aria-hidden="true" />
                  <button type="button" style={{ width: hitWidth }} onClick={() => setSelected(momentKey(item))} aria-pressed={item === active} aria-label={`${gestureLabel(item)}, ${time(item.start_seconds)} to ${time(item.end_seconds ?? item.start_seconds + item.duration_seconds)}. Review evidence.`}>
                    <time>{time(item.start_seconds)}</time><span><GestureIcon type={type} /></span>
                  </button>
                </div>)}
              </div>
            </div>;
          })}
        </div>
      </div>
      <p className="practice-gesture-timeline-note">Choose a moment to watch what happened and see what to practise.</p>
      <GestureReview event={active} token={token} />
    </> : <p className="practice-empty">{tracking?.status === "reliable" ? "No gesture issues were identified in this recording." : "For clearer gesture feedback, record with your face, arms and torso in view."}</p>}
  </section>;
}
